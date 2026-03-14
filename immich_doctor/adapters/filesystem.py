from __future__ import annotations

import os
from pathlib import Path

from immich_doctor.core.models import CheckResult, CheckStatus


class FilesystemAdapter:
    def validate_directory(self, name: str, path: Path) -> CheckResult:
        if not path.exists():
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message="Configured path does not exist.",
                details={"path": str(path)},
            )
        if not path.is_dir():
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message="Configured path is not a directory.",
                details={"path": str(path)},
            )
        return CheckResult(
            name=name,
            status=CheckStatus.PASS,
            message="Configured directory exists.",
            details={"path": str(path)},
        )

    def validate_writable_directory(self, name: str, path: Path) -> CheckResult:
        if not path.exists():
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message="Backup target path does not exist.",
                details={"path": str(path)},
            )
        if not path.is_dir():
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message="Backup target path is not a directory.",
                details={"path": str(path)},
            )
        if not os.access(path, os.W_OK):
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message="Backup target path is not writable for the current process.",
                details={"path": str(path)},
            )
        return CheckResult(
            name=name,
            status=CheckStatus.PASS,
            message="Backup target path is writable.",
            details={"path": str(path)},
        )

    def is_child_path(self, parent: Path, child: Path) -> bool:
        try:
            child.resolve().relative_to(parent.resolve())
        except ValueError:
            return False
        return True

