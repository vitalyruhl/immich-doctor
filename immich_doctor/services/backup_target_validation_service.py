from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from immich_doctor.adapters.external_tools import ExternalToolsAdapter
from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.backup.core.job_models import BackgroundJobState
from immich_doctor.backup.targets.models import (
    BackupTargetConfig,
    BackupTargetLastTestResult,
    BackupTargetMountStrategy,
    BackupTargetType,
    BackupTargetVerificationStatus,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.services.backup_job_service import BackgroundJobRuntime, ManagedJobHandle
from immich_doctor.services.backup_target_settings_service import BackupTargetSettingsService
from immich_doctor.services.backup_transport_service import BackupTransportService


def _validation_job_type(target_id: str) -> str:
    return f"backup_target_validation:{target_id}"


@dataclass(slots=True)
class BackupTargetValidationService:
    runtime: BackgroundJobRuntime
    target_settings: BackupTargetSettingsService = field(
        default_factory=BackupTargetSettingsService
    )
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    tools: ExternalToolsAdapter = field(default_factory=ExternalToolsAdapter)

    def get_validation(self, settings: AppSettings, *, target_id: str) -> dict[str, object]:
        active = self.runtime.active_job(job_type=_validation_job_type(target_id))
        if active is not None:
            return active.result

        target = self.target_settings.get_target(settings, target_id=target_id)
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "jobId": None,
            "targetId": target_id,
            "state": target.verification_status.value,
            "summary": target.last_test_result.summary
            if target.last_test_result
            else "Target validation has not run yet.",
            "checks": target.last_test_result.details.get("checks", [])
            if target.last_test_result
            else [],
            "warnings": target.last_test_result.warnings if target.last_test_result else [],
        }

    def start_validation(self, settings: AppSettings, *, target_id: str) -> dict[str, object]:
        active = self.runtime.active_job(job_type=_validation_job_type(target_id))
        if active is not None:
            return active.result

        target = self.target_settings.get_target(settings, target_id=target_id)
        pending = {
            "generatedAt": datetime.now(UTC).isoformat(),
            "jobId": None,
            "targetId": target_id,
            "targetType": target.target_type.value,
            "state": BackgroundJobState.PENDING.value,
            "summary": "Target validation queued.",
            "checks": [],
            "warnings": [],
        }
        updated_target = target.model_copy(
            update={"verification_status": BackupTargetVerificationStatus.RUNNING}
        )
        self.target_settings.save_target(settings, updated_target)
        record = self.runtime.start_job(
            settings,
            job_type=_validation_job_type(target_id),
            initial_result=pending,
            summary="Target validation queued.",
            runner=lambda handle: self._run_validation(handle, target_id=target_id),
        )
        pending["jobId"] = record.job_id
        return pending

    def validate_target_now(
        self,
        settings: AppSettings,
        *,
        target: BackupTargetConfig,
    ) -> dict[str, object]:
        checks = self._checks_for_target(settings, target=target)
        summary = self._summary_from_checks(checks)
        status = self._status_from_checks(checks)
        warnings = [check.message for check in checks if check.status == CheckStatus.WARN]
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "jobId": None,
            "targetId": target.target_id,
            "targetType": target.target_type.value,
            "state": status.value,
            "summary": summary,
            "checks": [check.to_dict() for check in checks],
            "warnings": warnings,
        }

    def _run_validation(self, handle: ManagedJobHandle, *, target_id: str) -> dict[str, object]:
        target = self.target_settings.get_target(handle.settings, target_id=target_id)
        result = self.validate_target_now(handle.settings, target=target)
        last_test_result = BackupTargetLastTestResult(
            checkedAt=result["generatedAt"],
            status=self._verification_status_from_state(result["state"]),
            summary=str(result["summary"]),
            warnings=list(result["warnings"]),
            details={"checks": list(result["checks"])},
        )
        updated_target = target.model_copy(
            update={
                "verification_status": self._verification_status_from_state(result["state"]),
                "last_test_result": last_test_result,
            }
        )
        self.target_settings.save_target(handle.settings, updated_target)
        return result

    def _checks_for_target(
        self,
        settings: AppSettings,
        *,
        target: BackupTargetConfig,
    ) -> list[CheckResult]:
        checks = [
            CheckResult(
                name="target_enabled",
                status=CheckStatus.PASS if target.enabled else CheckStatus.WARN,
                message="Target is enabled." if target.enabled else "Target is disabled.",
            )
        ]
        if target.target_type == BackupTargetType.LOCAL:
            checks.extend(self._local_checks(target))
        elif target.target_type in {BackupTargetType.SSH, BackupTargetType.RSYNC}:
            checks.extend(self._remote_checks(settings, target))
        else:
            checks.extend(self._smb_checks(target))
        return checks

    def _local_checks(self, target: BackupTargetConfig) -> list[CheckResult]:
        if target.transport.path is None:
            return [
                CheckResult(
                    name="local_path",
                    status=CheckStatus.FAIL,
                    message="Local target path is missing.",
                )
            ]
        path = Path(target.transport.path)
        checks = [self.filesystem.validate_creatable_directory("local_target_path", path)]
        free_space = self.filesystem.free_space_bytes(path)
        if free_space is not None:
            checks.append(
                CheckResult(
                    name="local_target_free_space",
                    status=CheckStatus.PASS,
                    message="Free space could be inspected on the local target.",
                    details={"free_space_bytes": free_space},
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="local_target_free_space",
                    status=CheckStatus.WARN,
                    message="Free space could not be determined for the local target.",
                )
            )
        return checks

    def _remote_checks(
        self,
        settings: AppSettings,
        target: BackupTargetConfig,
    ) -> list[CheckResult]:
        checks = []
        if target.transport.auth_mode is None:
            checks.append(
                CheckResult(
                    name="remote_auth_mode",
                    status=CheckStatus.FAIL,
                    message="Remote target auth mode is missing.",
                )
            )
            return checks
        if target.transport.auth_mode.value != "private_key":
            checks.append(
                CheckResult(
                    name="remote_auth_mode",
                    status=CheckStatus.SKIP,
                    message="Only private_key auth mode is implemented for remote execution.",
                )
            )
            return checks
        checks.extend(self.tools.validate_required_tools(["ssh", "rsync"]))

        try:
            transport = BackupTransportService(self.target_settings.secrets)
            with transport.prepared_remote_connection(settings, target) as material:
                remote_path = transport.quoted_remote_path(material.remote_path)
                probe_command = (
                    f"mkdir -p {remote_path} && "
                    f"probe={remote_path}/.immich-doctor-write-probe && "
                    "touch \"$probe\" && rm -f \"$probe\""
                )
                probe = transport.run_remote_command(material, probe_command)
                if probe.returncode == 0:
                    checks.append(
                        CheckResult(
                            name="remote_write_probe",
                            status=CheckStatus.PASS,
                            message="Remote target write probe succeeded.",
                        )
                    )
                else:
                    checks.append(
                        CheckResult(
                            name="remote_write_probe",
                            status=CheckStatus.FAIL,
                            message="Remote target write probe failed.",
                            details={"stderr": probe.stderr},
                        )
                    )
                free_space_command = f"df -Pk {remote_path} | tail -1"
                free_space = transport.run_remote_command(material, free_space_command)
                if free_space.returncode == 0:
                    checks.append(
                        CheckResult(
                            name="remote_free_space",
                            status=CheckStatus.PASS,
                            message="Remote free space command succeeded.",
                            details={"raw": free_space.stdout.strip()},
                        )
                    )
                else:
                    checks.append(
                        CheckResult(
                            name="remote_free_space",
                            status=CheckStatus.WARN,
                            message="Remote free space command failed.",
                            details={"stderr": free_space.stderr},
                        )
                    )
                for warning in material.warnings:
                    checks.append(
                        CheckResult(
                            name="remote_security_warning",
                            status=CheckStatus.WARN,
                            message=warning,
                        )
                    )
        except ValueError as exc:
            checks.append(
                CheckResult(
                    name="remote_transport",
                    status=CheckStatus.SKIP,
                    message=str(exc),
                )
            )
        return checks

    def _smb_checks(self, target: BackupTargetConfig) -> list[CheckResult]:
        checks = [
            CheckResult(
                name="smb_execution_mode",
                status=CheckStatus.SKIP,
                message=(
                    "SMB targets are configuration and validation only in this phase; "
                    "productive SMB execution is disabled."
                ),
            )
        ]
        if target.transport.mount_strategy == BackupTargetMountStrategy.PRE_MOUNTED_PATH:
            if target.transport.mounted_path is None:
                checks.append(
                    CheckResult(
                        name="smb_mounted_path",
                        status=CheckStatus.FAIL,
                        message="SMB pre-mounted targets require a mounted path.",
                    )
                )
            else:
                checks.append(
                    self.filesystem.validate_creatable_directory(
                        "smb_mounted_path",
                        Path(target.transport.mounted_path),
                    )
                )
        else:
            checks.append(
                CheckResult(
                    name="smb_mount_plan",
                    status=CheckStatus.WARN,
                    message="SMB system mount validation is planning-only in this phase.",
                )
            )
        return checks

    def _status_from_checks(self, checks: list[CheckResult]) -> BackgroundJobState:
        statuses = {check.status for check in checks}
        if CheckStatus.FAIL in statuses:
            return BackgroundJobState.FAILED
        if CheckStatus.SKIP in statuses and statuses <= {CheckStatus.PASS, CheckStatus.SKIP}:
            return BackgroundJobState.UNSUPPORTED
        if CheckStatus.WARN in statuses:
            return BackgroundJobState.PARTIAL
        return BackgroundJobState.COMPLETED

    def _summary_from_checks(self, checks: list[CheckResult]) -> str:
        state = self._status_from_checks(checks)
        if state == BackgroundJobState.COMPLETED:
            return "Target validation completed successfully."
        if state == BackgroundJobState.UNSUPPORTED:
            return "Target validation is only partially supported for this target."
        if state == BackgroundJobState.FAILED:
            return "Target validation failed."
        return "Target validation completed with warnings."

    def _verification_status_from_state(
        self,
        state: str,
    ) -> BackupTargetVerificationStatus:
        if state == BackgroundJobState.COMPLETED.value:
            return BackupTargetVerificationStatus.READY
        if state == BackgroundJobState.FAILED.value:
            return BackupTargetVerificationStatus.FAILED
        if state == BackgroundJobState.UNSUPPORTED.value:
            return BackupTargetVerificationStatus.UNSUPPORTED
        return BackupTargetVerificationStatus.WARNING
