from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    import pwd
except ImportError:  # pragma: no cover - not available on Windows
    pwd = None

try:
    from grp import getgrgid
except ImportError:  # pragma: no cover - not available on Windows
    getgrgid = None

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport
from immich_doctor.core.paths import configured_immich_paths, runtime_paths
from immich_doctor.services.health_service import HealthService


@dataclass(slots=True)
class RuntimeValidationService:
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    health: HealthService = field(default_factory=HealthService)

    def run(self, settings: AppSettings) -> ValidationReport:
        checks: list[CheckResult] = []
        checks.extend(self.health.run_ping().checks)
        checks.append(self._validate_identity())
        checks.extend(self._validate_source_paths(settings))
        checks.extend(self._validate_runtime_paths(settings))
        checks.extend(self._validate_optional_config_path(settings))
        checks.extend(self._validate_database(settings))

        return ValidationReport(
            command="runtime validate",
            checks=checks,
            metadata={"environment": settings.environment},
        )

    def _validate_identity(self) -> CheckResult:
        uid = getattr(os, "getuid", lambda: None)()
        gid = getattr(os, "getgid", lambda: None)()

        return CheckResult(
            name="runtime_identity",
            status=CheckStatus.PASS,
            message="Runtime identity information collected.",
            details={
                "uid": uid,
                "gid": gid,
                "username": self._username(uid),
                "group": self._group_name(gid),
                "cwd": os.getcwd(),
                "umask": self._current_umask(),
            },
        )

    def _validate_source_paths(self, settings: AppSettings) -> list[CheckResult]:
        checks: list[CheckResult] = []
        source_paths = configured_immich_paths(settings)

        if not source_paths:
            return [
                CheckResult(
                    name="source_paths_configured",
                    status=CheckStatus.FAIL,
                    message="No source paths are configured for runtime validation.",
                )
            ]

        checks.append(
            CheckResult(
                name="source_paths_configured",
                status=CheckStatus.PASS,
                message="Source paths are configured for runtime validation.",
                details={"count": len(source_paths)},
            )
        )

        for name, path in source_paths.items():
            checks.append(self.filesystem.validate_directory(name=name, path=path))
            checks.append(
                self.filesystem.validate_readable_directory(
                    name=f"{name}_readable",
                    path=path,
                )
            )
            checks.append(
                self.filesystem.validate_source_mount_mode(
                    name=f"{name}_mount_mode",
                    path=path,
                )
            )

        root = settings.immich_library_root
        if root is not None:
            checks.extend(self._validate_child_relationships(settings, root))

        return checks

    def _validate_child_relationships(
        self,
        settings: AppSettings,
        root: object,
    ) -> list[CheckResult]:
        child_paths = {
            "immich_uploads_path": settings.immich_uploads_path,
            "immich_thumbs_path": settings.immich_thumbs_path,
            "immich_profile_path": settings.immich_profile_path,
            "immich_video_path": settings.immich_video_path,
        }

        checks: list[CheckResult] = []
        for name, path in child_paths.items():
            if path is None:
                checks.append(
                    CheckResult(
                        name=f"{name}_under_root",
                        status=CheckStatus.SKIP,
                        message=f"{name} not configured; relationship check skipped.",
                    )
                )
                continue

            is_child = self.filesystem.is_child_path(parent=root, child=path)
            checks.append(
                CheckResult(
                    name=f"{name}_under_root",
                    status=CheckStatus.PASS if is_child else CheckStatus.FAIL,
                    message="Configured path is inside the library root."
                    if is_child
                    else "Configured path is outside the library root.",
                    details={"root": str(root), "path": str(path)},
                )
            )
        return checks

    def _validate_runtime_paths(self, settings: AppSettings) -> list[CheckResult]:
        checks: list[CheckResult] = []
        for name, path in runtime_paths(settings).items():
            checks.append(self.filesystem.validate_directory(name=name, path=path))
            checks.append(
                self.filesystem.validate_readable_directory(
                    name=f"{name}_readable",
                    path=path,
                )
            )
            checks.append(
                self.filesystem.validate_writable_directory(
                    name=f"{name}_writable",
                    path=path,
                )
            )

        if settings.backup_target_path is None:
            checks.append(
                CheckResult(
                    name="backup_target_runtime",
                    status=CheckStatus.WARN,
                    message="Backup target path is not configured for runtime validation.",
                )
            )
        else:
            checks.append(
                self.filesystem.validate_directory(
                    name="backup_target_path",
                    path=settings.backup_target_path,
                )
            )
            checks.append(
                self.filesystem.validate_readable_directory(
                    name="backup_target_path_readable",
                    path=settings.backup_target_path,
                )
            )
            checks.append(
                self.filesystem.validate_writable_directory(
                    name="backup_target_path_writable",
                    path=settings.backup_target_path,
                )
            )

        return checks

    def _validate_optional_config_path(self, settings: AppSettings) -> list[CheckResult]:
        if settings.config_path is None:
            return [
                CheckResult(
                    name="config_path",
                    status=CheckStatus.SKIP,
                    message="Optional config path is not configured.",
                )
            ]

        return [
            self.filesystem.validate_directory(name="config_path", path=settings.config_path),
            self.filesystem.validate_readable_directory(
                name="config_path_readable",
                path=settings.config_path,
            ),
        ]

    def _validate_database(self, settings: AppSettings) -> list[CheckResult]:
        host, port = settings.postgres_target()
        dsn = settings.postgres_dsn_value()

        if host is None or port is None:
            return [
                CheckResult(
                    name="postgres_target",
                    status=CheckStatus.WARN,
                    message="Database host or DSN not configured; database checks skipped.",
                )
            ]

        checks = [
            self.postgres.validate_host_resolution(host),
            self.postgres.validate_tcp_connection(
                host=host,
                port=port,
                timeout_seconds=settings.postgres_connect_timeout_seconds,
            ),
        ]

        if dsn is None:
            checks.append(
                CheckResult(
                    name="postgres_connection",
                    status=CheckStatus.WARN,
                    message="Database login credentials are incomplete; login check skipped.",
                )
            )
        else:
            checks.append(
                self.postgres.validate_connection(
                    dsn=dsn,
                    timeout_seconds=settings.postgres_connect_timeout_seconds,
                )
            )

        return checks

    def _username(self, uid: int | None) -> str | None:
        if uid is None:
            return None
        if pwd is None:
            return None
        try:
            return pwd.getpwuid(uid).pw_name
        except KeyError:
            return None

    def _group_name(self, gid: int | None) -> str | None:
        if gid is None:
            return None
        if getgrgid is None:
            return None
        try:
            return getgrgid(gid).gr_name
        except KeyError:
            return None

    def _current_umask(self) -> str | None:
        if not hasattr(os, "umask"):
            return None
        current = os.umask(0)
        os.umask(current)
        return format(current, "03o")
