"""File backup domain primitives and rsync-based local backup foundation."""

from immich_doctor.backup.files.executor import (
    FileBackupExecutionError,
    LocalFileBackupExecutor,
)
from immich_doctor.backup.files.models import FileBackupExecutionPlan, FileBackupRequest
from immich_doctor.backup.files.rsync import RsyncCommandBuilder, RsyncCommandSpec
from immich_doctor.backup.files.versioning import VersionedDestinationBuilder

__all__ = [
    "FileBackupExecutionError",
    "FileBackupExecutionPlan",
    "FileBackupRequest",
    "LocalFileBackupExecutor",
    "RsyncCommandBuilder",
    "RsyncCommandSpec",
    "VersionedDestinationBuilder",
]
