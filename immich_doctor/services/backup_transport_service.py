from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from immich_doctor.backup.targets.models import (
    BackupTargetAuthMode,
    BackupTargetConfig,
    BackupTargetKnownHostMode,
)
from immich_doctor.backup.targets.secrets import LocalSecretStore
from immich_doctor.core.config import AppSettings


@dataclass(slots=True, frozen=True)
class RemoteConnectionMaterial:
    remote_host_reference: str
    remote_shell_argv: tuple[str, ...]
    remote_path: str
    warnings: tuple[str, ...] = ()

    def ssh_command(self, command: str) -> tuple[str, ...]:
        return (*self.remote_shell_argv, self.remote_host_reference, command)


@dataclass(slots=True)
class BackupTransportService:
    secrets: LocalSecretStore

    @contextmanager
    def prepared_remote_connection(
        self,
        settings: AppSettings,
        target: BackupTargetConfig,
    ) -> Iterator[RemoteConnectionMaterial]:
        if target.transport.auth_mode == BackupTargetAuthMode.PASSWORD:
            raise ValueError(
                "Password auth mode is not implemented for SSH and rsync execution."
            )
        host = target.transport.host
        username = target.transport.username
        remote_path = target.transport.remote_path
        if host is None or username is None or remote_path is None:
            raise ValueError("Remote target is missing host, username, or remote path.")

        ssh_args = [
            "ssh",
            "-p",
            str(target.transport.port or 22),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "NumberOfPasswordPrompts=0",
        ]
        warnings: list[str] = []
        key_path: Path | None = None
        if target.transport.auth_mode == BackupTargetAuthMode.PRIVATE_KEY:
            if target.transport.private_key_secret_ref is None:
                raise ValueError("Remote target is missing a private key secret reference.")
            private_key_material = self.secrets.load_secret_material(
                settings,
                secret_id=target.transport.private_key_secret_ref.secret_id,
            )
            with tempfile.NamedTemporaryFile(
                "wb",
                prefix="immich-doctor-key-",
                delete=False,
            ) as handle:
                handle.write(private_key_material.encode("utf-8"))
                key_path = Path(handle.name)
            try:
                os.chmod(key_path, 0o600)
            except OSError:
                pass
            ssh_args.extend(["-i", key_path.as_posix()])
        elif target.transport.auth_mode != BackupTargetAuthMode.AGENT:
            raise ValueError("Remote target is missing a supported auth mode.")

        if target.transport.known_host_mode == BackupTargetKnownHostMode.STRICT:
            known_hosts_path = self.ensure_known_hosts_path(target)
            ssh_args.extend(
                [
                    "-o",
                    "StrictHostKeyChecking=yes",
                    "-o",
                    f"UserKnownHostsFile={known_hosts_path.as_posix()}",
                ]
            )
        elif target.transport.known_host_mode == BackupTargetKnownHostMode.ACCEPT_NEW:
            known_hosts_path = self.ensure_known_hosts_path(target)
            ssh_args.extend(
                [
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    f"UserKnownHostsFile={known_hosts_path.as_posix()}",
                ]
            )
        elif target.transport.known_host_mode == BackupTargetKnownHostMode.DISABLED:
            warnings.append(
                "Known-host verification is explicitly disabled for this target."
            )
            ssh_args.extend(
                [
                    "-o",
                    "StrictHostKeyChecking=no",
                ]
            )
        else:
            raise ValueError(
                "Remote target is missing a supported known-host mode."
            )

        try:
            yield RemoteConnectionMaterial(
                remote_host_reference=f"{username}@{host}",
                remote_shell_argv=tuple(ssh_args),
                remote_path=remote_path,
                warnings=tuple(warnings),
            )
        finally:
            if key_path is not None:
                key_path.unlink(missing_ok=True)

    def run_remote_command(
        self,
        material: RemoteConnectionMaterial,
        command: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            material.ssh_command(command),
            check=False,
            capture_output=True,
            text=True,
        )

    def remote_shell_command(self, material: RemoteConnectionMaterial) -> tuple[str, ...]:
        return material.remote_shell_argv

    def destination_reference(
        self,
        material: RemoteConnectionMaterial,
        destination_path: str,
    ) -> str:
        normalized = destination_path.rstrip("/")
        return f"{material.remote_host_reference}:{normalized}"

    def quoted_remote_path(self, path: str) -> str:
        return shlex.quote(path)

    def known_hosts_path(self, target: BackupTargetConfig) -> Path:
        if target.transport.known_host_reference:
            return Path(target.transport.known_host_reference).expanduser()
        return Path.home() / ".ssh" / "known_hosts"

    def ensure_known_hosts_path(self, target: BackupTargetConfig) -> Path:
        known_hosts_path = self.known_hosts_path(target)
        known_hosts_path.parent.mkdir(parents=True, exist_ok=True)
        known_hosts_path.touch(exist_ok=True)
        try:
            os.chmod(known_hosts_path.parent, 0o700)
        except OSError:
            pass
        try:
            os.chmod(known_hosts_path, 0o600)
        except OSError:
            pass
        return known_hosts_path
