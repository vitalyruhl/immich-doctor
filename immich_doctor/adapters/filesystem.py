from __future__ import annotations

import errno
import hashlib
import os
import shutil
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from immich_doctor.core.models import CheckResult, CheckStatus


class DirectoryScanTimeoutError(RuntimeError):
    """Raised when a directory usage scan exceeds the configured deadline."""


class DirectoryScanCanceledError(RuntimeError):
    """Raised when a directory usage scan is canceled safely."""


@dataclass(slots=True, frozen=True)
class DirectoryUsageSummary:
    total_bytes: int
    file_count: int
    directory_count: int
    other_entry_count: int
    error_count: int
    error_samples: tuple[dict[str, str], ...]


class FilesystemAdapter:
    def path_exists(self, path: Path) -> bool:
        return path.exists()

    def stat_path(self, path: Path) -> os.stat_result:
        return path.stat()

    def read_probe(self, path: Path, size: int = 8192) -> bytes:
        with path.open("rb") as handle:
            return handle.read(size)

    def delete_file(self, path: Path) -> None:
        path.unlink()

    def move_file(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(source.as_posix(), destination.as_posix())

    def compute_file_checksum(
        self,
        path: Path,
        *,
        algorithm: str = "sha256",
        chunk_size: int = 1024 * 1024,
    ) -> str:
        digest = hashlib.new(algorithm)
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def add_read_permissions(self, path: Path) -> None:
        current_mode = path.stat().st_mode
        path.chmod(current_mode | stat.S_IRUSR | stat.S_IRGRP)

    def set_permissions(self, path: Path, mode: int) -> None:
        path.chmod(mode)

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

    def validate_creatable_directory(self, name: str, path: Path) -> CheckResult:
        if path.exists():
            return self.validate_writable_directory(name, path)

        parent = path.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent

        if not parent.exists():
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message="Configured directory cannot be created because no parent path exists.",
                details={"path": str(path)},
            )

        probe_path = parent / f".immich-doctor-dir-probe-{uuid4().hex}"
        try:
            probe_path.mkdir()
        except PermissionError:
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message="Configured directory cannot be created due to permissions.",
                details={"path": str(path), "parent": str(parent), "reason": "permission_denied"},
            )
        except OSError as exc:
            reason = self._write_failure_reason(exc)
            return CheckResult(
                name=name,
                status=CheckStatus.FAIL,
                message=reason["message"],
                details={"path": str(path), "parent": str(parent), "reason": reason["reason"]},
            )
        finally:
            try:
                probe_path.rmdir()
            except OSError:
                pass

        return CheckResult(
            name=name,
            status=CheckStatus.PASS,
            message="Configured directory can be created and written by the current process.",
            details={"path": str(path), "parent": str(parent)},
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

    def nearest_existing_path(self, path: Path) -> Path | None:
        current = path
        while not current.exists() and current != current.parent:
            current = current.parent
        if current.exists():
            return current
        return None

    def free_space_bytes(self, path: Path) -> int | None:
        existing_path = self.nearest_existing_path(path)
        if existing_path is None:
            return None
        try:
            usage = shutil.disk_usage(existing_path)
        except OSError:
            return None
        return usage.free

    def scan_directory_usage(
        self,
        path: Path,
        *,
        on_file: Callable[[Path, int], None] | None = None,
        on_progress: Callable[[dict[str, object]], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
        deadline_monotonic: float | None = None,
        progress_interval_seconds: float = 0.5,
        progress_every_files: int = 1000,
        error_sample_limit: int = 5,
    ) -> DirectoryUsageSummary:
        stack: list[Path] = [path]
        total_bytes = 0
        file_count = 0
        directory_count = 0
        other_entry_count = 0
        error_count = 0
        error_samples: list[dict[str, str]] = []
        last_progress = 0.0

        while stack:
            self._raise_if_scan_should_stop(
                cancel_requested=cancel_requested,
                deadline_monotonic=deadline_monotonic,
            )
            current_directory = stack.pop()
            directory_count += 1

            try:
                with os.scandir(current_directory) as iterator:
                    for entry in iterator:
                        self._raise_if_scan_should_stop(
                            cancel_requested=cancel_requested,
                            deadline_monotonic=deadline_monotonic,
                        )
                        try:
                            entry_path = Path(entry.path)
                            if entry.is_dir(follow_symlinks=False):
                                stack.append(entry_path)
                            elif entry.is_file(follow_symlinks=False):
                                entry_stat = entry.stat(follow_symlinks=False)
                                total_bytes += entry_stat.st_size
                                file_count += 1
                                if on_file is not None:
                                    on_file(entry_path, entry_stat.st_size)
                            else:
                                other_entry_count += 1
                        except OSError as exc:
                            error_count += 1
                            if len(error_samples) < error_sample_limit:
                                error_samples.append(
                                    {
                                        "path": entry.path,
                                        "message": str(exc),
                                    }
                                )

                        now = time.monotonic()
                        if on_progress is not None and (
                            file_count == 1
                            or file_count % progress_every_files == 0
                            or now - last_progress >= progress_interval_seconds
                        ):
                            on_progress(
                                {
                                    "current": file_count,
                                    "unit": "files",
                                    "message": "Collecting storage size data.",
                                    "current_path": entry.path,
                                    "bytes": total_bytes,
                                    "directories": directory_count,
                                }
                            )
                            last_progress = now
            except OSError as exc:
                error_count += 1
                if len(error_samples) < error_sample_limit:
                    error_samples.append(
                        {
                            "path": current_directory.as_posix(),
                            "message": str(exc),
                        }
                    )

        if on_progress is not None:
            on_progress(
                {
                    "current": file_count,
                    "unit": "files",
                    "message": "Storage size collection completed.",
                    "current_path": path.as_posix(),
                    "bytes": total_bytes,
                    "directories": directory_count,
                }
            )

        return DirectoryUsageSummary(
            total_bytes=total_bytes,
            file_count=file_count,
            directory_count=directory_count,
            other_entry_count=other_entry_count,
            error_count=error_count,
            error_samples=tuple(error_samples),
        )

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

    def _raise_if_scan_should_stop(
        self,
        *,
        cancel_requested: Callable[[], bool] | None,
        deadline_monotonic: float | None,
    ) -> None:
        if cancel_requested is not None and cancel_requested():
            raise DirectoryScanCanceledError("Directory usage scan was canceled.")
        if deadline_monotonic is not None and time.monotonic() > deadline_monotonic:
            raise DirectoryScanTimeoutError("Directory usage scan timed out.")
