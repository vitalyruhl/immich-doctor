from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport
from immich_doctor.core.paths import configured_immich_paths, runtime_paths


@dataclass(slots=True)
class StoragePathsCheckService:
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
            checks.append(
                CheckResult(
                    name="source_paths_configured",
                    status=CheckStatus.PASS,
                    message="Source paths are configured.",
                    details={"count": len(source_paths)},
                )
            )

        for name, path in source_paths.items():
            checks.append(self.filesystem.validate_directory(name=name, path=path))

        checks.extend(self._validate_child_relationships(settings))

        for name, path in runtime_paths(settings).items():
            checks.append(self.filesystem.validate_directory(name=name, path=path))

        if settings.config_path is None:
            checks.append(
                CheckResult(
                    name="config_path",
                    status=CheckStatus.SKIP,
                    message="Optional config path is not configured.",
                )
            )
        else:
            checks.append(
                self.filesystem.validate_directory(
                    name="config_path",
                    path=settings.config_path,
                )
            )

        return ValidationReport(
            domain="storage.paths",
            action="check",
            summary="Storage path checks completed.",
            checks=checks,
            metadata={"environment": settings.environment},
        )

    def _validate_child_relationships(self, settings: AppSettings) -> list[CheckResult]:
        root = settings.immich_library_root
        if root is None:
            return []

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
