from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from immich_doctor.adapters.external_tools import ExternalToolsAdapter
from immich_doctor.core.models import CheckStatus
from immich_doctor.services.backup_job_service import BackgroundJobRuntime


@dataclass(slots=True)
class BackupRuntimeCapabilityService:
    runtime: BackgroundJobRuntime
    tools: ExternalToolsAdapter = field(default_factory=ExternalToolsAdapter)

    def probe_rsync(self) -> dict[str, object]:
        check = self.tools.inspect_runtime_tool(
            "rsync",
            version_argv=["rsync", "--version"],
        )
        summary = (
            "Local rsync is available in the doctor runtime."
            if check.status == CheckStatus.PASS
            else "Local rsync is not available in the doctor runtime."
        )
        snapshot = {
            "tool": "rsync",
            "checkedAt": datetime.now(UTC).isoformat(),
            "available": check.status == CheckStatus.PASS,
            "summary": summary,
            "check": check.to_dict(),
        }
        self.runtime.set_capability_snapshot("rsync", snapshot)
        return snapshot

    def probe_ssh_agent(self) -> dict[str, object]:
        checked_at = datetime.now(UTC).isoformat()
        socket_path = os.getenv("SSH_AUTH_SOCK")
        if not socket_path:
            snapshot = {
                "capability": "sshAgent",
                "checkedAt": checked_at,
                "available": False,
                "summary": (
                    "No forwarded SSH agent is available in the doctor runtime. "
                    "Mount the host agent socket and set SSH_AUTH_SOCK, or use a "
                    "private key secret."
                ),
                "details": {"state": "missing_env"},
            }
            self.runtime.set_capability_snapshot("sshAgent", snapshot)
            return snapshot

        socket = Path(socket_path)
        if not socket.exists():
            snapshot = {
                "capability": "sshAgent",
                "checkedAt": checked_at,
                "available": False,
                "summary": (
                    "SSH_AUTH_SOCK is set in the doctor runtime, but the forwarded "
                    "agent socket path "
                    "does not exist."
                ),
                "details": {"state": "missing_path", "socket": socket_path},
            }
            self.runtime.set_capability_snapshot("sshAgent", snapshot)
            return snapshot

        try:
            socket_stat = socket.stat()
        except OSError as exc:
            snapshot = {
                "capability": "sshAgent",
                "checkedAt": checked_at,
                "available": False,
                "summary": f"SSH agent socket could not be inspected in the doctor runtime: {exc}",
                "details": {"state": "unreadable", "socket": socket_path},
            }
            self.runtime.set_capability_snapshot("sshAgent", snapshot)
            return snapshot

        if not stat.S_ISSOCK(socket_stat.st_mode):
            snapshot = {
                "capability": "sshAgent",
                "checkedAt": checked_at,
                "available": False,
                "summary": "SSH_AUTH_SOCK points to a path that is not a socket.",
                "details": {"state": "not_socket", "socket": socket_path},
            }
            self.runtime.set_capability_snapshot("sshAgent", snapshot)
            return snapshot

        ssh_add_check = self.tools.inspect_runtime_tool("ssh-add")
        if ssh_add_check.status != CheckStatus.PASS:
            snapshot = {
                "capability": "sshAgent",
                "checkedAt": checked_at,
                "available": False,
                "summary": (
                    "The runtime has an SSH agent socket, but `ssh-add` is not "
                    "available to verify it."
                ),
                "details": {"state": "missing_tool", "socket": socket_path},
                "check": ssh_add_check.to_dict(),
            }
            self.runtime.set_capability_snapshot("sshAgent", snapshot)
            return snapshot

        try:
            probe = subprocess.run(
                ["ssh-add", "-L"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
                env={**os.environ, "SSH_AUTH_SOCK": socket_path},
            )
        except OSError as exc:
            snapshot = {
                "capability": "sshAgent",
                "checkedAt": checked_at,
                "available": False,
                "summary": f"Forwarded SSH agent could not be queried in the doctor runtime: {exc}",
                "details": {"state": "unusable", "socket": socket_path},
            }
            self.runtime.set_capability_snapshot("sshAgent", snapshot)
            return snapshot
        except subprocess.TimeoutExpired:
            snapshot = {
                "capability": "sshAgent",
                "checkedAt": checked_at,
                "available": False,
                "summary": "Forwarded SSH agent did not respond in time.",
                "details": {"state": "timeout", "socket": socket_path},
            }
            self.runtime.set_capability_snapshot("sshAgent", snapshot)
            return snapshot

        identity_lines = [line.strip() for line in probe.stdout.splitlines() if line.strip()]
        combined_output = "\n".join(
            part for part in (probe.stdout.strip(), probe.stderr.strip()) if part
        )
        if probe.returncode == 0 and identity_lines:
            snapshot = {
                "capability": "sshAgent",
                "checkedAt": checked_at,
                "available": True,
                "summary": "Forwarded SSH agent is available in the doctor runtime.",
                "details": {
                    "state": "available",
                    "socket": socket_path,
                    "identityCount": len(identity_lines),
                },
            }
            self.runtime.set_capability_snapshot("sshAgent", snapshot)
            return snapshot

        if "The agent has no identities." in combined_output:
            snapshot = {
                "capability": "sshAgent",
                "checkedAt": checked_at,
                "available": False,
                "summary": (
                    "Forwarded SSH agent is reachable in the doctor runtime, but "
                    "no identities are loaded."
                ),
                "details": {"state": "no_identities", "socket": socket_path},
            }
            self.runtime.set_capability_snapshot("sshAgent", snapshot)
            return snapshot

        snapshot = {
            "capability": "sshAgent",
            "checkedAt": checked_at,
            "available": False,
            "summary": (
                "Forwarded SSH agent socket is present, but the doctor runtime could not query it."
            ),
            "details": {"state": "unusable", "socket": socket_path, "output": combined_output},
        }
        self.runtime.set_capability_snapshot("sshAgent", snapshot)
        return snapshot

    def trigger_startup_probe(self) -> dict[str, object]:
        return {
            "rsync": self.probe_rsync(),
            "sshAgent": self.probe_ssh_agent(),
        }

    def cached_rsync_snapshot(self) -> dict[str, object] | None:
        return self.runtime.get_capability_snapshot("rsync")

    def cached_ssh_agent_snapshot(self) -> dict[str, object] | None:
        return self.runtime.get_capability_snapshot("sshAgent")
