from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import os
from pathlib import Path
import subprocess

from immich_doctor.adapters.external_tools import ExternalToolsAdapter
from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.backup.core.job_models import BackgroundJobState
from immich_doctor.backup.targets.models import (
    BackupTargetAuthMode,
    BackupTargetKnownHostMode,
    BackupTargetConfig,
    BackupTargetLastTestResult,
    BackupTargetMountStrategy,
    BackupTargetType,
    BackupTargetVerificationStatus,
)
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.services.backup_job_service import BackgroundJobRuntime, ManagedJobHandle
from immich_doctor.services.backup_runtime_capability_service import (
    BackupRuntimeCapabilityService,
)
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
            return self._normalize_validation_result(active.result)

        target = self.target_settings.get_target(settings, target_id=target_id)
        if target.last_test_result is None:
            state = BackgroundJobState.PENDING.value
            summary = "Target validation has not run yet."
            checks: list[dict[str, object]] = []
            warnings: list[str] = []
            execution_support = self._default_execution_support(target)
        else:
            state = self._job_state_from_verification_status(
                target.last_test_result.status
            ).value
            summary = target.last_test_result.summary
            checks = target.last_test_result.details.get("checks", [])
            warnings = target.last_test_result.warnings
            execution_support = target.last_test_result.details.get(
                "executionSupport",
                self._default_execution_support(target),
            )
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "jobId": None,
            "targetId": target_id,
            "targetType": target.target_type.value,
            "state": state,
            "verificationStatus": target.verification_status.value,
            "summary": summary,
            "checks": checks,
            "warnings": warnings,
            "executionSupport": execution_support,
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
            "verificationStatus": BackupTargetVerificationStatus.RUNNING.value,
            "summary": "Target validation is pending.",
            "checks": [],
            "warnings": [],
            "executionSupport": self._default_execution_support(target),
        }
        updated_target = target.model_copy(
            update={"verification_status": BackupTargetVerificationStatus.RUNNING}
        )
        self.target_settings.save_target(settings, updated_target)
        record = self.runtime.start_job(
            settings,
            job_type=_validation_job_type(target_id),
            initial_result=pending,
            summary="Target validation is pending.",
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
        validation_checks = self._validation_relevant_checks(target, checks)
        execution_support = self._execution_support_from_checks(target, checks, validation_checks)
        summary = self._summary_from_checks(
            validation_checks,
            execution_support=execution_support,
        )
        status = self._status_from_checks(validation_checks)
        warnings = [
            check.message for check in validation_checks if check.status == CheckStatus.WARN
        ]
        return {
            "generatedAt": datetime.now(UTC).isoformat(),
            "jobId": None,
            "targetId": target.target_id,
            "targetType": target.target_type.value,
            "state": status.value,
            "verificationStatus": self._verification_status_from_state(status.value).value,
            "summary": summary,
            "checks": [check.to_dict() for check in checks],
            "warnings": warnings,
            "executionSupport": execution_support,
        }

    def _run_validation(self, handle: ManagedJobHandle, *, target_id: str) -> dict[str, object]:
        target = self.target_settings.get_target(handle.settings, target_id=target_id)
        result = self.validate_target_now(handle.settings, target=target)
        last_test_result = BackupTargetLastTestResult(
            checkedAt=result["generatedAt"],
            status=self._verification_status_from_state(result["state"]),
            summary=str(result["summary"]),
            warnings=list(result["warnings"]),
            details={
                "checks": list(result["checks"]),
                "executionSupport": dict(result["executionSupport"]),
            },
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
        if target.transport.auth_mode == BackupTargetAuthMode.PASSWORD:
            checks.append(
                CheckResult(
                    name="remote_auth_mode",
                    status=CheckStatus.SKIP,
                    message="Password auth mode is not implemented for remote execution.",
                )
            )
            return checks
        if target.transport.known_host_mode == BackupTargetKnownHostMode.DISABLED:
            checks.append(
                CheckResult(
                    name="remote_known_host_mode",
                    status=CheckStatus.WARN,
                    message="Known-host verification is disabled for this target.",
                )
            )
        ssh_tool_checks = self.tools.validate_required_tools(["ssh"])
        checks.extend(ssh_tool_checks)
        rsync_snapshot = BackupRuntimeCapabilityService(runtime=self.runtime).probe_rsync()
        rsync_check = self._rsync_execution_check(target, rsync_snapshot)
        checks.append(rsync_check)

        transport = BackupTransportService(self.target_settings.secrets)
        checks.extend(self._agent_checks(target))
        checks.extend(self._known_hosts_checks(target, transport))
        if any(
            check.status == CheckStatus.FAIL
            for check in checks
            if check.name in {"tool_ssh", "remote_agent_socket", "remote_known_hosts_path"}
        ):
            return checks

        try:
            with transport.prepared_remote_connection(settings, target) as material:
                remote_path = transport.quoted_remote_path(material.remote_path)
                probe_command = (
                    f"mkdir -p {remote_path} && "
                    f"probe={remote_path}/.immich-doctor-write-probe && "
                    'touch "$probe" && rm -f "$probe"'
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
                            message=(
                                "SSH connection reached the target, but the configured remote "
                                "destination could not be created or written."
                            ),
                            details={"stderr": probe.stderr, "stdout": probe.stdout},
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
                            details={"stderr": free_space.stderr, "stdout": free_space.stdout},
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
        except subprocess.TimeoutExpired:
            checks.append(
                CheckResult(
                    name="remote_transport",
                    status=CheckStatus.FAIL,
                    message="SSH validation timed out before the remote probe completed.",
                )
            )
        except OSError as exc:
            checks.append(
                CheckResult(
                    name="remote_transport",
                    status=CheckStatus.FAIL,
                    message=f"SSH validation could not start the local ssh process: {exc}",
                )
            )
        except ValueError as exc:
            checks.append(
                CheckResult(
                    name="remote_transport",
                    status=CheckStatus.FAIL,
                    message=str(exc),
                )
            )
        return checks

    def _smb_checks(self, target: BackupTargetConfig) -> list[CheckResult]:
        if target.transport.mount_strategy == BackupTargetMountStrategy.PRE_MOUNTED_PATH:
            checks: list[CheckResult] = []
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
                free_space = self.filesystem.free_space_bytes(
                    Path(target.transport.mounted_path)
                )
                if free_space is not None:
                    checks.append(
                        CheckResult(
                            name="smb_mounted_path_free_space",
                            status=CheckStatus.PASS,
                            message="Free space could be inspected on the mounted SMB path.",
                            details={"free_space_bytes": free_space},
                        )
                    )
                else:
                    checks.append(
                        CheckResult(
                            name="smb_mounted_path_free_space",
                            status=CheckStatus.WARN,
                            message="Free space could not be determined for the mounted SMB path.",
                        )
                    )
            checks.append(
                CheckResult(
                    name="smb_execution_mode",
                    status=CheckStatus.PASS,
                    message=(
                        "SMB pre-mounted mode is executable as a path-like mounted "
                        "destination when the mounted path is usable."
                    ),
                )
            )
            checks.append(
                CheckResult(
                    name="smb_auth_mode",
                    status=CheckStatus.PASS,
                    message="SMB pre-mounted mode relies on an already authenticated mount.",
                )
            )
            return checks

        checks = [
            CheckResult(
                name="smb_execution_mode",
                status=CheckStatus.SKIP,
                message=(
                    "SMB system mount is planned only and is not executable in the current safe subset. "
                    "Only pre-mounted path execution is currently supported."
                ),
            )
        ]
        if target.transport.username:
            checks.append(
                CheckResult(
                    name="smb_username",
                    status=CheckStatus.PASS,
                    message="SMB system-mount username is configured.",
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="smb_username",
                    status=CheckStatus.FAIL,
                    message="SMB system-mount targets require a username.",
                )
            )
        if target.transport.password_secret_ref is None:
            checks.append(
                CheckResult(
                    name="smb_password_secret_ref",
                    status=CheckStatus.FAIL,
                    message="SMB system-mount targets require a password secret reference.",
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="smb_password_secret_ref",
                    status=CheckStatus.PASS,
                    message="SMB system-mount credentials are stored via a secret reference.",
                )
            )
        checks.append(
            CheckResult(
                name="smb_mount_plan",
                status=CheckStatus.PASS,
                message="SMB system-mount checks remain mount-planning only in this phase.",
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

    def _summary_from_checks(
        self,
        checks: list[CheckResult],
        *,
        execution_support: dict[str, object],
    ) -> str:
        state = self._status_from_checks(checks)
        execution_suffix = ""
        if execution_support.get("supported") is False and execution_support.get("summary"):
            execution_suffix = f" {execution_support['summary']}"
        if state == BackgroundJobState.COMPLETED:
            return (
                "Target validation completed for currently implemented connectivity and "
                f"destination checks.{execution_suffix}"
            )
        if state == BackgroundJobState.UNSUPPORTED:
            reason = self._first_check_message(checks, {CheckStatus.SKIP})
            if reason:
                return f"Target validation is unsupported in this phase: {reason}{execution_suffix}"
            return "Target validation is unsupported for part of this target in the current phase."
        if state == BackgroundJobState.FAILED:
            reason = self._first_check_message(checks, {CheckStatus.FAIL})
            if reason:
                return f"Target validation failed: {reason}"
            return "Target validation failed."
        reason = self._first_check_message(checks, {CheckStatus.WARN})
        if reason:
            return f"Target validation completed with warnings: {reason}{execution_suffix}"
        return "Target validation completed with warnings for currently implemented checks."

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

    def _job_state_from_verification_status(
        self,
        status: BackupTargetVerificationStatus,
    ) -> BackgroundJobState:
        if status == BackupTargetVerificationStatus.READY:
            return BackgroundJobState.COMPLETED
        if status == BackupTargetVerificationStatus.WARNING:
            return BackgroundJobState.PARTIAL
        if status == BackupTargetVerificationStatus.FAILED:
            return BackgroundJobState.FAILED
        if status == BackupTargetVerificationStatus.RUNNING:
            return BackgroundJobState.RUNNING
        if status == BackupTargetVerificationStatus.UNSUPPORTED:
            return BackgroundJobState.UNSUPPORTED
        return BackgroundJobState.PENDING

    def _normalize_validation_result(
        self,
        result: dict[str, object],
    ) -> dict[str, object]:
        normalized = dict(result)
        verification_status = normalized.get("verificationStatus")
        if verification_status is None:
            state = str(normalized.get("state") or "")
            verification_status = self._verification_status_from_state(state).value
            normalized["verificationStatus"] = verification_status
        if normalized.get("executionSupport") is None:
            normalized["executionSupport"] = self._default_execution_support_from_result(
                normalized
            )
        return normalized

    def _first_check_message(
        self,
        checks: list[CheckResult],
        statuses: set[CheckStatus],
    ) -> str | None:
        for check in checks:
            if check.status in statuses:
                return check.message
        return None

    def _agent_checks(self, target: BackupTargetConfig) -> list[CheckResult]:
        if target.transport.auth_mode != BackupTargetAuthMode.AGENT:
            return []
        socket_path = os.getenv("SSH_AUTH_SOCK")
        if not socket_path:
            return [
                CheckResult(
                    name="remote_agent_socket",
                    status=CheckStatus.FAIL,
                    message=(
                        "SSH agent auth is selected, but SSH_AUTH_SOCK is not available in the doctor runtime."
                    ),
                )
            ]
        socket = Path(socket_path)
        if not socket.exists():
            return [
                CheckResult(
                    name="remote_agent_socket",
                    status=CheckStatus.FAIL,
                    message=(
                        f"SSH agent auth is selected, but the agent socket path does not exist: {socket_path}"
                    ),
                )
            ]
        return [
            CheckResult(
                name="remote_agent_socket",
                status=CheckStatus.PASS,
                message="SSH agent socket is available in the doctor runtime.",
                details={"socket": socket_path},
            )
        ]

    def _known_hosts_checks(
        self,
        target: BackupTargetConfig,
        transport: BackupTransportService,
    ) -> list[CheckResult]:
        if target.transport.known_host_mode == BackupTargetKnownHostMode.DISABLED:
            return []
        try:
            known_hosts_path = transport.ensure_known_hosts_path(target)
        except OSError as exc:
            return [
                CheckResult(
                    name="remote_known_hosts_path",
                    status=CheckStatus.FAIL,
                    message=f"Known-hosts file path could not be prepared: {exc}",
                )
            ]
        return [
            CheckResult(
                name="remote_known_hosts_path",
                status=CheckStatus.PASS,
                message="Known-hosts file path is available to the doctor runtime.",
                details={"path": known_hosts_path.as_posix()},
            )
        ]

    def _validation_relevant_checks(
        self,
        target: BackupTargetConfig,
        checks: list[CheckResult],
    ) -> list[CheckResult]:
        if target.target_type not in {BackupTargetType.SSH, BackupTargetType.RSYNC}:
            return checks
        return [check for check in checks if check.name != "tool_rsync"]

    def _execution_support_from_checks(
        self,
        target: BackupTargetConfig,
        checks: list[CheckResult],
        validation_checks: list[CheckResult],
    ) -> dict[str, object]:
        if target.target_type == BackupTargetType.LOCAL:
            return {
                "supported": True,
                "state": "supported",
                "summary": "Asset-aware local check and sync execution is supported.",
            }
        if target.target_type == BackupTargetType.SMB:
            if (
                target.transport.mount_strategy == BackupTargetMountStrategy.PRE_MOUNTED_PATH
                and target.transport.mounted_path is not None
            ):
                return {
                    "supported": True,
                    "state": "supported",
                    "summary": "Mounted path check and sync execution is supported.",
                }
            return {
                "supported": False,
                "state": "unsupported",
                "summary": (
                    "SMB system mount remains planned only and is not executable in the "
                    "current safe subset."
                ),
            }
        if target.transport.auth_mode == BackupTargetAuthMode.PASSWORD:
            return {
                "supported": False,
                "state": "unsupported",
                "summary": (
                    "Password-based SSH/rsync execution is not implemented in this phase."
                ),
            }
        validation_state = self._status_from_checks(validation_checks)
        if validation_state not in {BackgroundJobState.COMPLETED, BackgroundJobState.PARTIAL}:
            return {
                "supported": False,
                "state": "blocked",
                "summary": (
                    "Remote execution readiness is unavailable until connectivity and "
                    "destination validation succeed."
                ),
            }
        rsync_check = next((check for check in checks if check.name == "tool_rsync"), None)
        if rsync_check is not None and rsync_check.status != CheckStatus.PASS:
            return {
                "supported": False,
                "state": "blocked",
                "summary": rsync_check.message,
                "details": rsync_check.details,
            }
        return {
            "supported": True,
            "state": "supported",
            "summary": "Files-only remote execution is supported.",
        }

    def _rsync_execution_check(
        self,
        target: BackupTargetConfig,
        snapshot: dict[str, object],
    ) -> CheckResult:
        check_details = snapshot.get("check")
        details = (
            dict(check_details["details"])
            if isinstance(check_details, dict)
            and isinstance(check_details.get("details"), dict)
            else {"tool": "rsync"}
        )
        message = (
            "SSH target reachable, but files-only remote execution is blocked because local "
            "rsync is not available on PATH."
            if target.target_type == BackupTargetType.SSH
            else "Rsync-over-SSH target reachable, but remote execution is blocked because local rsync is not available on PATH."
        )
        if snapshot.get("available") is True:
            version = details.get("version")
            return CheckResult(
                name="tool_rsync",
                status=CheckStatus.PASS,
                message=(
                    "Local rsync is available in the doctor runtime."
                    if not version
                    else f"Local rsync is available in the doctor runtime ({version})."
                ),
                details=details,
            )
        return CheckResult(
            name="tool_rsync",
            status=CheckStatus.WARN,
            message=message,
            details=details,
        )

    def _default_execution_support(
        self,
        target: BackupTargetConfig,
    ) -> dict[str, object]:
        if target.target_type == BackupTargetType.LOCAL:
            return {
                "supported": True,
                "state": "supported",
                "summary": "Asset-aware local check and sync execution is supported.",
            }
        if target.target_type == BackupTargetType.SMB:
            if (
                target.transport.mount_strategy == BackupTargetMountStrategy.PRE_MOUNTED_PATH
                and target.transport.mounted_path is not None
            ):
                return {
                    "supported": True,
                    "state": "supported",
                    "summary": "Mounted path check and sync execution is supported.",
                }
            return {
                "supported": False,
                "state": "unsupported",
                "summary": (
                    "SMB system mount remains planned only and is not executable in the "
                    "current safe subset."
                ),
            }
        return {
            "supported": False,
            "state": "unknown",
            "summary": "Remote execution readiness has not been checked yet.",
        }

    def _default_execution_support_from_result(
        self,
        result: dict[str, object],
    ) -> dict[str, object]:
        target_type = result.get("targetType")
        if target_type == BackupTargetType.LOCAL.value:
            return {
                "supported": True,
                "state": "supported",
                "summary": "Asset-aware local check and sync execution is supported.",
            }
        if target_type == BackupTargetType.SMB.value:
            return {
                "supported": False,
                "state": "unknown",
                "summary": "SMB execution readiness has not been checked yet.",
            }
        return {
            "supported": False,
            "state": "unknown",
            "summary": "Remote execution readiness has not been checked yet.",
        }
