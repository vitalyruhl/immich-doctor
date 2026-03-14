"""Local rsync execution abstractions for future file backup workflows."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Protocol

from immich_doctor.backup.core.models import BackupArtifact, BackupResult, BackupTarget
from immich_doctor.backup.files.models import FileBackupExecutionPlan
from immich_doctor.backup.files.rsync import RsyncCommandBuilder, RsyncCommandSpec


class CommandRunner(Protocol):
    """Protocol for safe subprocess-based command execution."""

    def __call__(
        self,
        argv: tuple[str, ...],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        """Run the provided argument list and return a completed process."""


@dataclass(slots=True)
class FileBackupExecutionError(RuntimeError):
    """Raised when local file backup execution cannot proceed safely."""

    message: str
    argv: tuple[str, ...] = ()
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)

    def to_dict(self) -> dict[str, object]:
        return {
            "message": self.message,
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(slots=True)
class LocalFileBackupExecutor:
    """Executes a prepared local rsync file backup plan without CLI exposure."""

    command_builder: RsyncCommandBuilder = field(default_factory=RsyncCommandBuilder)
    command_runner: CommandRunner = subprocess.run

    def is_available(self) -> bool:
        """Report whether the configured rsync executable is available in PATH."""

        return shutil.which(self.command_builder.executable) is not None

    def build_command(self, plan: FileBackupExecutionPlan) -> RsyncCommandSpec:
        """Return the safe argument vector that would be executed for the plan."""

        return self.command_builder.build(plan)

    def execute(self, plan: FileBackupExecutionPlan) -> BackupResult:
        """Execute a local rsync backup plan and return a structural backup result."""

        if not self.is_available():
            raise FileBackupExecutionError(
                message=f"Required executable is not available: {self.command_builder.executable}"
            )

        plan.destination_path.parent.mkdir(parents=True, exist_ok=True)
        command = self.build_command(plan)
        completed = self.command_runner(
            command.argv,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise FileBackupExecutionError(
                message=f"Rsync execution failed with exit code {completed.returncode}.",
                argv=command.argv,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

        artifact_target = BackupTarget(
            kind="local",
            reference=str(plan.backup_root_path),
            display_name=plan.backup_root_path.name,
        )
        artifact = BackupArtifact(
            name=plan.request.source_label,
            kind="file_archive",
            target=artifact_target,
            relative_path=plan.artifact_relative_path,
        )
        return BackupResult(
            domain="backup.files",
            action="run",
            status="success",
            summary="File backup execution completed.",
            context=plan.request.context,
            artifacts=(artifact,),
            details={
                "backup_root_path": plan.backup_root_path.as_posix(),
                "destination_path": plan.destination_path.as_posix(),
                "command": list(command.argv),
            },
        )
