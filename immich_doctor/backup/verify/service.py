from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.adapters.external_tools import ExternalToolsAdapter
from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport


@dataclass(slots=True)
class BackupVerifyService:
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    external_tools: ExternalToolsAdapter = field(default_factory=ExternalToolsAdapter)

    def run(self, settings: AppSettings) -> ValidationReport:
        checks: list[CheckResult] = []

        if settings.backup_target_path is None:
            checks.append(
                CheckResult(
                    name="backup_target_configured",
                    status=CheckStatus.FAIL,
                    message="Backup target path is not configured.",
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="backup_target_configured",
                    status=CheckStatus.PASS,
                    message="Backup target path is configured.",
                    details={"path": str(settings.backup_target_path)},
                )
            )
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

        if settings.required_external_tools:
            checks.extend(
                self.external_tools.validate_required_tools(settings.required_external_tools)
            )
        else:
            checks.append(
                CheckResult(
                    name="required_external_tools",
                    status=CheckStatus.SKIP,
                    message="No required external tools configured.",
                )
            )

        return ValidationReport(
            domain="backup",
            action="verify",
            summary="Backup verification completed.",
            checks=checks,
            metadata={"environment": settings.environment},
        )
