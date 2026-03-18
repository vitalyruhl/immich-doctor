"""Safe rsync command construction for local file backup execution."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

from immich_doctor.backup.files.models import FileBackupExecutionPlan

_FORBIDDEN_RSYNC_FLAGS = frozenset(
    {
        "--delete",
        "--delete-before",
        "--delete-during",
        "--delete-delay",
        "--delete-after",
        "--remove-source-files",
    }
)


def _normalize_source_path(path: Path) -> str:
    return f"{path.as_posix().rstrip('/')}/"


@dataclass(slots=True, frozen=True)
class RsyncCommandSpec:
    """Captures the rsync executable and argument vector for safe subprocess usage."""

    argv: tuple[str, ...]


@dataclass(slots=True)
class RsyncCommandBuilder:
    """Builds non-destructive rsync commands for local-to-local file backup runs."""

    executable: str = "rsync"
    base_options: tuple[str, ...] = ("--archive", "--hard-links", "--numeric-ids")
    extra_options: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        forbidden = _FORBIDDEN_RSYNC_FLAGS.intersection(self.base_options + self.extra_options)
        if forbidden:
            forbidden_flags = ", ".join(sorted(forbidden))
            raise ValueError(f"Destructive rsync flags are not allowed: {forbidden_flags}")

    def build(self, plan: FileBackupExecutionPlan) -> RsyncCommandSpec:
        argv = (
            self.executable,
            *self.base_options,
            *self.extra_options,
            _normalize_source_path(plan.request.source_path),
            plan.destination_path.as_posix(),
        )
        return RsyncCommandSpec(argv=argv)

    def build_transfer(
        self,
        *,
        source_path: Path,
        destination_reference: str,
        remote_shell_argv: tuple[str, ...] | None = None,
    ) -> RsyncCommandSpec:
        extra_options = list(self.extra_options)
        if "--stats" not in extra_options:
            extra_options.append("--stats")
        if remote_shell_argv is not None:
            extra_options.extend(("-e", shlex.join(remote_shell_argv)))
        argv = (
            self.executable,
            *self.base_options,
            *tuple(extra_options),
            _normalize_source_path(source_path),
            destination_reference,
        )
        return RsyncCommandSpec(argv=argv)
