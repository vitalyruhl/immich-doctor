from __future__ import annotations

import errno
import os
import stat
from pathlib import Path
from uuid import uuid4

from immich_doctor.core.models import CheckResult, CheckStatus


class FilesystemAdapter:
    def validate_directory(self, name: str, path: Path) -> CheckResult:
        directory_state = self._directory_state(name=name, path=path)
        if directory_state is not None:
            return directory_state

        return CheckResult(
            name=name,
            status=CheckStatus.PASS,
            message="Configured directory exists.",
            details={"path": str(path)},
        )

    def validate_readable_directory(self, name: str, path: Path) -> CheckResult:
        directory_state = self._directory_state(name=name, path=path)
        if directory_state is not None:
            return directory_state

        try:
            with os.scandir(path) as iterator:
                next(iterator, None)
        except PermissionError:
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message="Configured directory exists but is not readable.",
                details={"path": str(path)},
            )
        except OSError as exc:
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message=f"Configured directory could not be inspected: {exc.strerror or exc}.",
                details={"path": str(path)},
            )

        return CheckResult(
            name=name,
            status=CheckStatus.PASS,
            message="Configured directory is readable.",
            details={"path": str(path)},
        )

    def validate_writable_directory(self, name: str, path: Path) -> CheckResult:
        directory_state = self._directory_state(name=name, path=path)
        if directory_state is not None:
            return directory_state

        probe_path = path / f".immich-doctor-write-probe-{uuid4().hex}"
        try:
            with probe_path.open("x", encoding="utf-8") as handle:
                handle.write("probe")
        except PermissionError:
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message="Configured directory exists but is not writable.",
                details={"path": str(path), "reason": "permission_denied"},
            )
        except OSError as exc:
            reason = self._write_failure_reason(exc)
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message=reason["message"],
                details={"path": str(path), "reason": reason["reason"]},
            )
        finally:
            try:
                probe_path.unlink(missing_ok=True)
            except OSError:
                pass

        return CheckResult(
            name=name,
            status=CheckStatus.PASS,
            message="Configured directory is writable.",
            details={"path": str(path)},
        )

    def validate_source_mount_mode(self, name: str, path: Path) -> CheckResult:
        directory_state = self._directory_state(name=name, path=path)
        if directory_state is not None:
            return directory_state

        if os.access(path, os.W_OK):
            return CheckResult(
                name=name,
                status=CheckStatus.WARN,
                message="Source directory is writable; a read-only mount is recommended.",
                details={"path": str(path)},
            )

        return CheckResult(
            name=name,
            status=CheckStatus.PASS,
            message="Source directory is not writable for the current process.",
            details={"path": str(path)},
        )

    def is_child_path(self, parent: Path, child: Path) -> bool:
        try:
            child.resolve().relative_to(parent.resolve())
        except ValueError:
            return False
        return True

    def _directory_state(self, name: str, path: Path) -> CheckResult | None:
        try:
            path_stat = path.stat()
        except FileNotFoundError:
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message="Configured path does not exist.",
                details={"path": str(path)},
            )
        except PermissionError:
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message="Configured path exists but cannot be accessed due to permissions.",
                details={"path": str(path)},
            )
        except OSError as exc:
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message=f"Configured path could not be inspected: {exc.strerror or exc}.",
                details={"path": str(path)},
            )

        if not stat.S_ISDIR(path_stat.st_mode):
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message="Configured path is not a directory.",
                details={"path": str(path)},
            )

        return None

    def _write_failure_reason(self, exc: OSError) -> dict[str, str]:
        if exc.errno == errno.EROFS:
            return {
                "reason": "read_only_filesystem",
                "message": "Configured directory is on a read-only filesystem.",
            }
        if exc.errno in {errno.EACCES, errno.EPERM}:
            return {
                "reason": "permission_denied",
                "message": "Configured directory exists but is not writable.",
            }
        if exc.errno == errno.ENOENT:
            return {
                "reason": "missing_path",
                "message": "Configured directory does not exist.",
            }
        return {
            "reason": "write_probe_failed",
            "message": f"Configured directory write probe failed: {exc.strerror or exc}.",
        }
