"""Local rsync execution abstractions for future file backup workflows."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
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


class FileBackupExecutionError(RuntimeError):
    """Raised when local file backup execution cannot proceed safely."""


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
                f"Required executable is not available: {self.command_builder.executable}"
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
                f"Rsync execution failed with exit code {completed.returncode}."
            )

        artifact_target = BackupTarget(
            kind="local",
            reference=str(plan.destination_path),
            display_name=plan.destination_path.name,
        )
        artifact = BackupArtifact(
            name=plan.destination_path.name,
            kind="file_archive",
            target=artifact_target,
            relative_path=Path(plan.destination_path.name),
        )
        return BackupResult(
            status="success",
            summary="File backup execution completed.",
            context=plan.request.context,
            artifacts=(artifact,),
        )
