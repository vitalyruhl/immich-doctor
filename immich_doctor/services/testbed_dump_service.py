from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePath, PureWindowsPath

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from pydantic import BaseModel, ConfigDict, Field

from immich_doctor.backup.core.job_models import BackgroundJobState
from immich_doctor.core.config import AppSettings


class TestbedDumpServiceError(RuntimeError):
    """Raised when testbed dump import cannot proceed safely."""

    __test__ = False


class TestbedDumpOverview(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    __test__ = False

    enabled: bool
    environment: str
    can_import: bool = Field(alias="canImport")
    init_mode: str = Field(alias="initMode")
    default_path: str | None = Field(default=None, alias="defaultPath")
    default_format: str = Field(alias="defaultFormat")
    auto_import_on_empty: bool = Field(alias="autoImportOnEmpty")
    summary: str


class TestbedDumpImportResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    __test__ = False

    state: BackgroundJobState
    classification: str
    summary: str
    requested_path: str = Field(alias="requestedPath")
    effective_path: str = Field(alias="effectivePath")
    dump_format: str = Field(alias="dumpFormat")
    generated_at: str = Field(alias="generatedAt")
    db_was_empty: bool = Field(alias="dbWasEmpty")
    expected_skipped_statements: int = Field(alias="expectedSkippedStatements")
    structural_error_count: int = Field(alias="structuralErrorCount")
    meaningful_error_count: int = Field(alias="meaningfulErrorCount")
    warnings: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class TestbedDumpImportService:
    __test__ = False

    def get_overview(self, settings: AppSettings) -> TestbedDumpOverview:
        enabled = self._is_testbed_environment(settings)
        can_import = enabled and bool(settings.testbed_dump_path)
        if not enabled:
            summary = "Testbed dump import is available only in the dev-testbed environment."
        elif settings.testbed_init_mode.upper() != "FROM_DUMP":
            summary = "Testbed dump import is available, but auto-init is disabled by init mode."
        elif settings.testbed_dump_path:
            summary = "The testbed can auto-load the configured dump into an empty database."
        else:
            summary = "No default dump path is configured for the current testbed."

        return TestbedDumpOverview(
            enabled=enabled,
            environment=settings.environment,
            canImport=can_import,
            initMode=settings.testbed_init_mode,
            defaultPath=settings.testbed_dump_path,
            defaultFormat=settings.testbed_dump_format,
            autoImportOnEmpty=settings.testbed_auto_import_on_empty,
            summary=summary,
        )

    def maybe_auto_initialize(self, settings: AppSettings) -> TestbedDumpImportResult | None:
        if not self._is_testbed_environment(settings):
            return None
        if not settings.testbed_auto_import_on_empty:
            return None
        if settings.testbed_init_mode.upper() != "FROM_DUMP":
            return None
        if not settings.testbed_dump_path:
            raise TestbedDumpServiceError(
                "TESTBED_DUMP_PATH is required for automatic testbed dump initialization."
            )
        if not self.database_is_empty(settings):
            return None
        return self.import_dump(settings, force=False)

    def import_dump(
        self,
        settings: AppSettings,
        *,
        requested_path: str | None = None,
        dump_format: str | None = None,
        force: bool,
    ) -> TestbedDumpImportResult:
        self._ensure_testbed_enabled(settings)
        dsn = settings.postgres_dsn_value()
        if not dsn:
            raise TestbedDumpServiceError(
                "Database access is not configured for the current testbed environment."
            )

        db_was_empty = self.database_is_empty(settings)
        if not db_was_empty and not force:
            raise TestbedDumpServiceError(
                "Refusing to reload a non-empty testbed database without explicit force."
            )

        resolved_path = self.resolve_dump_path(settings, requested_path=requested_path)
        if not resolved_path.exists():
            raise TestbedDumpServiceError(f"Dump file not found: {resolved_path}")

        requested_display_path = requested_path or settings.testbed_dump_path or str(resolved_path)
        resolved_format = self._resolve_dump_format(
            path_text=requested_display_path,
            dump_format=dump_format or settings.testbed_dump_format,
        )
        result = self._restore_dump(
            settings,
            dsn=dsn,
            dump_path=resolved_path,
            requested_path=requested_display_path,
            dump_format=resolved_format,
            db_was_empty=db_was_empty,
        )
        if result.classification == "failure":
            raise TestbedDumpServiceError(result.summary)
        return result

    def database_is_empty(self, settings: AppSettings) -> bool:
        dsn = settings.postgres_dsn_value()
        if not dsn:
            raise TestbedDumpServiceError("Database access is not configured.")

        with psycopg.connect(
            dsn,
            connect_timeout=settings.postgres_connect_timeout_seconds,
            autocommit=True,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_type = 'BASE TABLE'
                      AND table_schema = 'public';
                    """
                )
                row = cursor.fetchone()
        return int(row[0]) == 0 if row is not None else True

    def resolve_dump_path(
        self,
        settings: AppSettings,
        *,
        requested_path: str | None = None,
    ) -> Path:
        path_text = (requested_path or settings.testbed_dump_path or "").strip()
        if not path_text:
            raise TestbedDumpServiceError("A dump path is required.")

        direct_path = Path(path_text)
        if direct_path.exists():
            return direct_path

        mapped_path = self._map_host_path_to_container(settings, path_text=path_text)
        if mapped_path is not None:
            return mapped_path
        return direct_path

    def _restore_dump(
        self,
        settings: AppSettings,
        *,
        dsn: str,
        dump_path: Path,
        requested_path: str,
        dump_format: str,
        db_was_empty: bool,
    ) -> TestbedDumpImportResult:
        conninfo = conninfo_to_dict(dsn)
        host = str(conninfo.get("host") or settings.db_host or "localhost")
        port = str(conninfo.get("port") or settings.db_port)
        user = str(conninfo.get("user") or settings.db_user or "postgres")
        database = str(conninfo.get("dbname") or settings.db_name or "postgres")
        password = str(conninfo.get("password") or settings.db_password.get_secret_value())
        env = {
            "PGPASSWORD": password,
            "PGCONNECT_TIMEOUT": str(settings.postgres_connect_timeout_seconds),
        }

        expected_skipped_statements = 0
        meaningful_error_count = 0
        structural_error_count = 0
        warning_lines: list[str] = []
        classification = "failure"
        prepared_dump_path: Path | None = None

        try:
            if dump_format == "custom":
                self._recreate_database(
                    host=host,
                    port=port,
                    user=user,
                    database=database,
                    env=env,
                )
                completed = self._run_command(
                    [
                        "pg_restore",
                        "--clean",
                        "--if-exists",
                        "--no-owner",
                        "--no-privileges",
                        "--host",
                        host,
                        "--port",
                        port,
                        "--username",
                        user,
                        "--dbname",
                        database,
                        str(dump_path),
                    ],
                    env=env,
                )
                combined_output = self._combined_output(completed)
                warning_lines = self._error_lines(combined_output)
                meaningful_error_count = len(warning_lines)
                if completed.returncode != 0 or not self._database_exists(
                    dsn=dsn,
                    connect_timeout=settings.postgres_connect_timeout_seconds,
                    database_name=database,
                ):
                    classification = "failure"
                elif meaningful_error_count > 0:
                    classification = "partial success"
                else:
                    classification = "success"
            else:
                target_database = database
                replay_path = dump_path
                if self._is_plain_sql_cluster_dump(dump_path):
                    prepared_dump_path, expected_skipped_statements = self._prepare_cluster_dump(
                        dump_path,
                        bootstrap_user=user,
                    )
                    replay_path = prepared_dump_path
                    target_database = "postgres"
                else:
                    self._recreate_database(
                        host=host,
                        port=port,
                        user=user,
                        database=database,
                        env=env,
                    )

                completed = self._run_command(
                    [
                        "psql",
                        "--host",
                        host,
                        "--port",
                        port,
                        "--username",
                        user,
                        "--dbname",
                        target_database,
                        "-v",
                        "ON_ERROR_STOP=0",
                        "-f",
                        str(replay_path),
                    ],
                    env=env,
                )
                combined_output = self._combined_output(completed)
                warning_lines = self._error_lines(combined_output)
                meaningful_error_count = len(warning_lines)
                structural_error_count = len(
                    [
                        line
                        for line in warning_lines
                        if any(
                            pattern in line.lower()
                            for pattern in (
                                "cannot drop the currently open database",
                                "current user cannot be dropped",
                                f'role "{user.lower()}" already exists',
                                f'database "{database.lower()}" already exists',
                            )
                        )
                    ]
                )
                if (
                    completed.returncode != 0
                    or structural_error_count > 0
                    or not self._database_exists(
                        dsn=dsn,
                        connect_timeout=settings.postgres_connect_timeout_seconds,
                        database_name=database,
                    )
                ):
                    classification = "failure"
                elif meaningful_error_count > 0:
                    classification = "partial success"
                else:
                    classification = "success"
        finally:
            if prepared_dump_path is not None and prepared_dump_path.exists():
                prepared_dump_path.unlink(missing_ok=True)

        summary = {
            "success": "Testbed dump import completed successfully.",
            "partial success": "Testbed dump import completed with replay warnings.",
            "failure": "Testbed dump import failed.",
        }[classification]

        return TestbedDumpImportResult(
            state={
                "success": BackgroundJobState.COMPLETED,
                "partial success": BackgroundJobState.PARTIAL,
                "failure": BackgroundJobState.FAILED,
            }[classification],
            classification=classification,
            summary=summary,
            requestedPath=requested_path,
            effectivePath=str(dump_path),
            dumpFormat=dump_format,
            generatedAt=datetime.now(UTC).isoformat(),
            dbWasEmpty=db_was_empty,
            expectedSkippedStatements=expected_skipped_statements,
            structuralErrorCount=structural_error_count,
            meaningfulErrorCount=meaningful_error_count,
            warnings=warning_lines,
        )

    def _ensure_testbed_enabled(self, settings: AppSettings) -> None:
        if not self._is_testbed_environment(settings):
            raise TestbedDumpServiceError(
                "Testbed dump import is available only in the dev-testbed environment."
            )

    def _is_testbed_environment(self, settings: AppSettings) -> bool:
        return settings.environment.strip().lower() == "dev-testbed"

    def _resolve_dump_format(self, *, path_text: str, dump_format: str) -> str:
        normalized = dump_format.strip().lower()
        if normalized != "auto":
            if normalized not in {"plain", "custom"}:
                raise TestbedDumpServiceError(f"Unsupported dump format option: {dump_format}")
            return normalized
        suffix = Path(path_text).suffix.lower()
        if suffix in {".dump", ".backup", ".bin"}:
            return "custom"
        if suffix == ".sql":
            return "plain"
        raise TestbedDumpServiceError(
            f"Could not infer dump format for {path_text}. Set TESTBED_DUMP_FORMAT explicitly."
        )

    def _map_host_path_to_container(
        self,
        settings: AppSettings,
        *,
        path_text: str,
    ) -> Path | None:
        if not settings.testbed_dump_mount_source or settings.testbed_container_dump_dir is None:
            return None

        relative_parts = self._relative_host_parts(
            path_text=path_text,
            mount_source=settings.testbed_dump_mount_source,
        )
        if relative_parts is None:
            return None
        return settings.testbed_container_dump_dir.joinpath(*relative_parts)

    def _relative_host_parts(
        self,
        *,
        path_text: str,
        mount_source: str,
    ) -> tuple[str, ...] | None:
        candidate = self._to_pure_path(path_text)
        source = self._to_pure_path(mount_source)
        try:
            relative = candidate.relative_to(source)
        except ValueError:
            return None
        return tuple(part for part in relative.parts if part not in {"", "."})

    def _to_pure_path(self, value: str) -> PurePath:
        if re.match(r"^[A-Za-z]:[\\/]", value):
            return PureWindowsPath(value)
        if "\\" in value:
            return PureWindowsPath(value)
        return PurePath(value)

    def _is_plain_sql_cluster_dump(self, dump_path: Path) -> bool:
        with dump_path.open("r", encoding="utf-8", errors="replace") as handle:
            header = "".join(handle.readline() for _ in range(80))
        return "PostgreSQL database cluster dump" in header

    def _prepare_cluster_dump(
        self,
        dump_path: Path,
        *,
        bootstrap_user: str,
    ) -> tuple[Path, int]:
        skipped = 0
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            suffix=".sql",
            delete=False,
        ) as handle:
            prepared_path = Path(handle.name)
            with dump_path.open("r", encoding="utf-8", errors="replace") as source:
                for raw_line in source:
                    line = raw_line.rstrip("\r\n")
                    if line == f"DROP ROLE IF EXISTS {bootstrap_user};":
                        handle.write(f"-- immich-doctor skipped bootstrap role drop: {line}\n")
                        skipped += 1
                        continue
                    if line == f"CREATE ROLE {bootstrap_user};":
                        handle.write(f"-- immich-doctor skipped bootstrap role create: {line}\n")
                        skipped += 1
                        continue
                    if line.startswith(f"ALTER ROLE {bootstrap_user} WITH "):
                        handle.write(f"-- immich-doctor skipped bootstrap role alter: {line}\n")
                        skipped += 1
                        continue
                    handle.write(line)
                    handle.write("\n")
        return prepared_path, skipped

    def _recreate_database(
        self,
        *,
        host: str,
        port: str,
        user: str,
        database: str,
        env: dict[str, str],
    ) -> None:
        self._run_command(
            [
                "dropdb",
                "--if-exists",
                "--force",
                "--host",
                host,
                "--port",
                port,
                "--username",
                user,
                database,
            ],
            env=env,
        )
        self._run_command(
            [
                "createdb",
                "--host",
                host,
                "--port",
                port,
                "--username",
                user,
                "--maintenance-db",
                "postgres",
                database,
            ],
            env=env,
        )

    def _database_exists(
        self,
        *,
        dsn: str,
        connect_timeout: int,
        database_name: str,
    ) -> bool:
        admin_dsn = make_conninfo(
            **{
                **conninfo_to_dict(dsn),
                "dbname": "postgres",
                "connect_timeout": str(connect_timeout),
            }
        )
        with psycopg.connect(
            admin_dsn,
            connect_timeout=connect_timeout,
            autocommit=True,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s;",
                    (database_name,),
                )
                return cursor.fetchone() is not None

    def _run_command(
        self,
        args: list[str],
        *,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            args,
            env={**os.environ, **env},
            check=False,
            capture_output=True,
            text=True,
        )
        return completed

    def _combined_output(self, completed: subprocess.CompletedProcess[str]) -> list[str]:
        lines: list[str] = []
        if completed.stdout:
            lines.extend(completed.stdout.splitlines())
        if completed.stderr:
            lines.extend(completed.stderr.splitlines())
        return lines

    def _error_lines(self, lines: list[str]) -> list[str]:
        return [line for line in lines if re.search(r"(?i)\b(error|fatal):", line)]
