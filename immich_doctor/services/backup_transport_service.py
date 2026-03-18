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
    HostKeyVerificationStrategy,
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
        if target.transport.auth_mode != BackupTargetAuthMode.PRIVATE_KEY:
            raise ValueError(
                "Only private_key auth mode is implemented for SSH and rsync execution."
            )
        if target.transport.private_key_secret_ref is None:
            raise ValueError("Remote target is missing a private key secret reference.")

        private_key_material = self.secrets.load_secret_material(
            settings,
            secret_id=target.transport.private_key_secret_ref.secret_id,
        )
        host = target.transport.host
        username = target.transport.username
        remote_path = target.transport.remote_path
        if host is None or username is None or remote_path is None:
            raise ValueError("Remote target is missing host, username, or remote path.")

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            prefix="immich-doctor-key-",
            delete=False,
        ) as handle:
            handle.write(private_key_material)
            key_path = Path(handle.name)

        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass

        known_hosts_path = self._known_hosts_path(target)
        ssh_args = [
            "ssh",
            "-p",
            str(target.transport.port or 22),
            "-i",
            key_path.as_posix(),
            "-o",
            "BatchMode=yes",
        ]
        warnings: list[str] = []
        if target.transport.host_key_verification == HostKeyVerificationStrategy.KNOWN_HOSTS:
            ssh_args.extend(
                [
                    "-o",
                    "StrictHostKeyChecking=yes",
                    "-o",
                    f"UserKnownHostsFile={known_hosts_path.as_posix()}",
                ]
            )
        elif (
            target.transport.host_key_verification
            == HostKeyVerificationStrategy.INSECURE_ACCEPT_ANY
        ):
            warnings.append(
                "Host key verification is explicitly configured as insecure_accept_any."
            )
            ssh_args.extend(
                [
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    f"UserKnownHostsFile={os.devnull}",
                ]
            )
        else:
            key_path.unlink(missing_ok=True)
            raise ValueError(
                "Pinned fingerprint host verification is not implemented for execution yet."
            )

        try:
            yield RemoteConnectionMaterial(
                remote_host_reference=f"{username}@{host}",
                remote_shell_argv=tuple(ssh_args),
                remote_path=remote_path,
                warnings=tuple(warnings),
            )
        finally:
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

    def _known_hosts_path(self, target: BackupTargetConfig) -> Path:
        if target.transport.host_key_reference:
            return Path(target.transport.host_key_reference).expanduser()
        return Path.home() / ".ssh" / "known_hosts"
