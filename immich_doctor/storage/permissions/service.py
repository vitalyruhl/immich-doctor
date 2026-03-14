from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport
from immich_doctor.core.paths import configured_immich_paths, runtime_paths


@dataclass(slots=True)
class StoragePermissionsCheckService:
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)

    def run(self, settings: AppSettings) -> ValidationReport:
        checks: list[CheckResult] = []
        source_paths = configured_immich_paths(settings)

        if not source_paths:
            checks.append(
                CheckResult(
                    name="source_paths_configured",
                    status=CheckStatus.FAIL,
                    message="No source paths are configured.",
                )
            )
        else:
            for name, path in source_paths.items():
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

        for name, path in runtime_paths(settings).items():
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

        if settings.config_path is None:
            checks.append(
                CheckResult(
                    name="config_path_permissions",
                    status=CheckStatus.SKIP,
                    message="Optional config path is not configured.",
                )
            )
        else:
            checks.append(
                self.filesystem.validate_readable_directory(
                    name="config_path_readable",
                    path=settings.config_path,
                )
            )
            checks.append(
                self.filesystem.validate_writable_directory(
                    name="config_path_writable",
                    path=settings.config_path,
                )
            )

        return ValidationReport(
            domain="storage.permissions",
            action="check",
            summary="Storage permission checks completed.",
            checks=checks,
            metadata={"environment": settings.environment},
        )
