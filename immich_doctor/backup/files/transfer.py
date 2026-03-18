from __future__ import annotations

import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from immich_doctor.backup.files.executor import FileBackupExecutionError
from immich_doctor.backup.files.rsync import RsyncCommandBuilder, RsyncCommandSpec

_NUMBER_PATTERN = re.compile(r"([0-9][0-9,]*)")


def _parse_first_int(value: str) -> int | None:
    match = _NUMBER_PATTERN.search(value)
    if match is None:
        return None
    return int(match.group(1).replace(",", ""))


@dataclass(slots=True, frozen=True)
class RsyncTransferMetrics:
    total_file_size_bytes: int | None = None
    transferred_file_size_bytes: int | None = None
    sent_bytes: int | None = None
    received_bytes: int | None = None
    file_count: int | None = None
    regular_files_transferred: int | None = None

    @property
    def bytes_transferred(self) -> int | None:
        if self.sent_bytes is None and self.received_bytes is None:
            return None
        return (self.sent_bytes or 0) + (self.received_bytes or 0)


@dataclass(slots=True, frozen=True)
class RsyncTransferResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str
    duration_seconds: float
    metrics: RsyncTransferMetrics


@dataclass(slots=True)
class ManagedRsyncTransferExecutor:
    command_builder: RsyncCommandBuilder = field(default_factory=RsyncCommandBuilder)

    def is_available(self) -> bool:
        return shutil.which(self.command_builder.executable) is not None

    def build_command(
        self,
        *,
        source_path: Path,
        destination_reference: str,
        remote_shell_argv: tuple[str, ...] | None = None,
    ) -> RsyncCommandSpec:
        return self.command_builder.build_transfer(
            source_path=source_path,
            destination_reference=destination_reference,
            remote_shell_argv=remote_shell_argv,
        )

    def execute(
        self,
        *,
        source_path: Path,
        destination_reference: str,
        create_local_parent: Path | None = None,
        remote_shell_argv: tuple[str, ...] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> RsyncTransferResult:
        if not self.is_available():
            raise FileBackupExecutionError(
                message=f"Required executable is not available: {self.command_builder.executable}"
            )

        if create_local_parent is not None:
            create_local_parent.mkdir(parents=True, exist_ok=True)

        command = self.build_command(
            source_path=source_path,
            destination_reference=destination_reference,
            remote_shell_argv=remote_shell_argv,
        )
        started = time.monotonic()
        process = subprocess.Popen(
            command.argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        canceled = False
        while process.poll() is None:
            if cancel_requested is not None and cancel_requested():
                canceled = True
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                break
            time.sleep(0.2)

        stdout, stderr = process.communicate()
        duration_seconds = round(time.monotonic() - started, 3)
        if canceled:
            raise FileBackupExecutionError(
                message="Rsync execution was canceled.",
                argv=command.argv,
                exit_code=process.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        if process.returncode != 0:
            raise FileBackupExecutionError(
                message=f"Rsync execution failed with exit code {process.returncode}.",
                argv=command.argv,
                exit_code=process.returncode,
                stdout=stdout,
                stderr=stderr,
            )

        return RsyncTransferResult(
            command=command.argv,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            metrics=self._parse_metrics(stdout, stderr),
        )

    def _parse_metrics(self, stdout: str, stderr: str) -> RsyncTransferMetrics:
        lines = [line.strip() for line in f"{stdout}\n{stderr}".splitlines() if line.strip()]
        payload: dict[str, int | None] = {
            "total_file_size_bytes": None,
            "transferred_file_size_bytes": None,
            "sent_bytes": None,
            "received_bytes": None,
            "file_count": None,
            "regular_files_transferred": None,
        }
        for line in lines:
            if line.startswith("Number of files:"):
                payload["file_count"] = _parse_first_int(line)
            elif line.startswith("Number of regular files transferred:"):
                payload["regular_files_transferred"] = _parse_first_int(line)
            elif line.startswith("Total file size:"):
                payload["total_file_size_bytes"] = _parse_first_int(line)
            elif line.startswith("Total transferred file size:"):
                payload["transferred_file_size_bytes"] = _parse_first_int(line)
            elif line.startswith("sent "):
                numbers = [int(item.replace(",", "")) for item in _NUMBER_PATTERN.findall(line)]
                if len(numbers) >= 2:
                    payload["sent_bytes"] = numbers[0]
                    payload["received_bytes"] = numbers[1]
        return RsyncTransferMetrics(**payload)
