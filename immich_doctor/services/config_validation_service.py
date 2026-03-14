from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport
from immich_doctor.core.paths import configured_immich_paths, runtime_paths


@dataclass(slots=True)
class ConfigValidationService:
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)

    def run(self, settings: AppSettings) -> ValidationReport:
        checks: list[CheckResult] = []
        immich_paths = configured_immich_paths(settings)

        if not immich_paths:
            checks.append(
                CheckResult(
                    name="immich_paths_configured",
                    status=CheckStatus.FAIL,
                    message="No Immich paths are configured.",
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="immich_paths_configured",
                    status=CheckStatus.PASS,
                    message="Immich paths are configured.",
                    details={"count": len(immich_paths)},
                )
            )

        for name, path in immich_paths.items():
            checks.append(self.filesystem.validate_directory(name=name, path=path))

        checks.extend(self._validate_runtime_paths(settings))
        checks.extend(self._validate_directory_relationships(settings))
        checks.append(self._validate_postgres(settings))

        return ValidationReport(
            command="config validate",
            checks=checks,
            metadata={"environment": settings.environment},
        )

    def _validate_runtime_paths(self, settings: AppSettings) -> list[CheckResult]:
        checks: list[CheckResult] = []
        for name, path in runtime_paths(settings).items():
            checks.append(
                CheckResult(
                    name=name,
                    status=CheckStatus.PASS,
                    message="Runtime path configured.",
                    details={"path": str(path)},
                )
            )
        return checks

    def _validate_directory_relationships(self, settings: AppSettings) -> list[CheckResult]:
        root = settings.immich_library_root
        if root is None:
            return [
                CheckResult(
                    name="immich_structure_relationships",
                    status=CheckStatus.SKIP,
                    message="Library root not configured; child path relationship checks skipped.",
                )
            ]

        child_paths = {
            "immich_uploads_path": settings.immich_uploads_path,
            "immich_thumbs_path": settings.immich_thumbs_path,
            "immich_profile_path": settings.immich_profile_path,
            "immich_video_path": settings.immich_video_path,
        }

        relationship_checks: list[CheckResult] = []
        for name, path in child_paths.items():
            if path is None:
                relationship_checks.append(
                    CheckResult(
                        name=f"{name}_under_root",
                        status=CheckStatus.SKIP,
                        message=f"{name} not configured; relationship check skipped.",
                    )
                )
                continue

            is_child = self.filesystem.is_child_path(parent=root, child=path)
            relationship_checks.append(
                CheckResult(
                    name=f"{name}_under_root",
                    status=CheckStatus.PASS if is_child else CheckStatus.FAIL,
                    message="Configured path is inside the library root."
                    if is_child
                    else "Configured path is outside the library root.",
                    details={"root": str(root), "path": str(path)},
                )
            )
        return relationship_checks

    def _validate_postgres(self, settings: AppSettings) -> CheckResult:
        dsn = settings.postgres_dsn_value()
        if not dsn:
            return CheckResult(
                name="postgres_connection",
                status=CheckStatus.WARN,
                message="PostgreSQL DSN not configured; connection check skipped.",
            )
        return self.postgres.validate_connection(dsn, settings.postgres_connect_timeout_seconds)
