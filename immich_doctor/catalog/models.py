from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class CatalogRootSpec:
    slug: str
    setting_name: str
    root_type: str
    path: Path


@dataclass(slots=True, frozen=True)
class CatalogFileObservation:
    relative_path: str
    parent_relative_path: str
    file_name: str
    extension: str | None
    size_bytes: int
    created_at_fs: str | None
    modified_at_fs: str | None
    file_type_guess: str
    media_class_guess: str
    zero_byte_flag: bool
    stat_device: str | None
    stat_inode: str | None
