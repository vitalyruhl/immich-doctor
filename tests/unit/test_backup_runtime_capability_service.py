from __future__ import annotations

import stat
from pathlib import Path
from subprocess import CompletedProcess

from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.services.backup_job_service import BackgroundJobRuntime
from immich_doctor.services.backup_runtime_capability_service import (
    BackupRuntimeCapabilityService,
)


def test_backup_runtime_capability_service_records_rsync_presence(
    monkeypatch, tmp_path: Path
) -> None:
    runtime = BackgroundJobRuntime()
    try:
        monkeypatch.setattr(
            "immich_doctor.services.backup_runtime_capability_service.ExternalToolsAdapter.inspect_runtime_tool",
            lambda self, tool, version_argv=None: CheckResult(
                name=f"tool_{tool}",
                status=CheckStatus.PASS,
                message="Required external tool is available in the runtime.",
                details={"tool": tool, "path": "/usr/bin/rsync", "version": "rsync 3.2.7"},
            ),
        )
        snapshot = BackupRuntimeCapabilityService(runtime=runtime).probe_rsync()
    finally:
        runtime.shutdown()

    assert snapshot["available"] is True
    assert snapshot["check"]["details"]["version"] == "rsync 3.2.7"


def test_backup_runtime_capability_service_records_rsync_absence(
    monkeypatch, tmp_path: Path
) -> None:
    runtime = BackgroundJobRuntime()
    try:
        monkeypatch.setattr(
            "immich_doctor.services.backup_runtime_capability_service.ExternalToolsAdapter.inspect_runtime_tool",
            lambda self, tool, version_argv=None: CheckResult(
                name=f"tool_{tool}",
                status=CheckStatus.FAIL,
                message="Required external tool `rsync` is not available on PATH.",
                details={"tool": tool},
            ),
        )
        snapshot = BackupRuntimeCapabilityService(runtime=runtime).probe_rsync()
    finally:
        runtime.shutdown()

    assert snapshot["available"] is False
    assert "not available" in snapshot["summary"]


def test_backup_runtime_capability_service_reports_missing_ssh_agent_socket(monkeypatch) -> None:
    runtime = BackgroundJobRuntime()
    try:
        monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
        snapshot = BackupRuntimeCapabilityService(runtime=runtime).probe_ssh_agent()
    finally:
        runtime.shutdown()

    assert snapshot["available"] is False
    assert snapshot["details"]["state"] == "missing_env"
    assert "Mount the host agent socket" in snapshot["summary"]


def test_backup_runtime_capability_service_reports_available_forwarded_ssh_agent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime = BackgroundJobRuntime()
    socket_path = tmp_path / "agent.sock"
    try:
        monkeypatch.setenv("SSH_AUTH_SOCK", socket_path.as_posix())
        monkeypatch.setattr(
            "immich_doctor.services.backup_runtime_capability_service.ExternalToolsAdapter.inspect_runtime_tool",
            lambda self, tool, version_argv=None: CheckResult(
                name=f"tool_{tool}",
                status=CheckStatus.PASS,
                message="Required external tool is available in the runtime.",
                details={"tool": tool, "path": f"/usr/bin/{tool}"},
            ),
        )
        monkeypatch.setattr(
            "pathlib.Path.exists",
            lambda self: self == socket_path,
        )
        monkeypatch.setattr(
            "pathlib.Path.stat",
            lambda self: type("StatResult", (), {"st_mode": stat.S_IFSOCK})(),
        )
        monkeypatch.setattr(
            "immich_doctor.services.backup_runtime_capability_service.subprocess.run",
            lambda *args, **kwargs: CompletedProcess(
                args=("ssh-add", "-L"),
                returncode=0,
                stdout="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest backup@example\n",
                stderr="",
            ),
        )
        snapshot = BackupRuntimeCapabilityService(runtime=runtime).probe_ssh_agent()
    finally:
        runtime.shutdown()

    assert snapshot["available"] is True
    assert snapshot["details"]["state"] == "available"
    assert snapshot["details"]["socket"] == socket_path.as_posix()


def test_backup_runtime_capability_service_reports_forwarded_agent_without_identities(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime = BackgroundJobRuntime()
    socket_path = tmp_path / "agent.sock"
    try:
        monkeypatch.setenv("SSH_AUTH_SOCK", socket_path.as_posix())
        monkeypatch.setattr(
            "immich_doctor.services.backup_runtime_capability_service.ExternalToolsAdapter.inspect_runtime_tool",
            lambda self, tool, version_argv=None: CheckResult(
                name=f"tool_{tool}",
                status=CheckStatus.PASS,
                message="Required external tool is available in the runtime.",
                details={"tool": tool, "path": f"/usr/bin/{tool}"},
            ),
        )
        monkeypatch.setattr(
            "pathlib.Path.exists",
            lambda self: self == socket_path,
        )
        monkeypatch.setattr(
            "pathlib.Path.stat",
            lambda self: type("StatResult", (), {"st_mode": stat.S_IFSOCK})(),
        )
        monkeypatch.setattr(
            "immich_doctor.services.backup_runtime_capability_service.subprocess.run",
            lambda *args, **kwargs: CompletedProcess(
                args=("ssh-add", "-L"),
                returncode=1,
                stdout="",
                stderr="The agent has no identities.\n",
            ),
        )
        snapshot = BackupRuntimeCapabilityService(runtime=runtime).probe_ssh_agent()
    finally:
        runtime.shutdown()

    assert snapshot["available"] is False
    assert snapshot["details"]["state"] == "no_identities"
    assert "no identities" in snapshot["summary"].lower()
