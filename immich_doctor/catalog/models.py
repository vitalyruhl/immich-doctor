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

    def to_dict(self) -> dict[str, object]:
        return {
            "relative_path": self.relative_path,
            "parent_relative_path": self.parent_relative_path,
            "file_name": self.file_name,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "created_at_fs": self.created_at_fs,
            "modified_at_fs": self.modified_at_fs,
            "file_type_guess": self.file_type_guess,
            "media_class_guess": self.media_class_guess,
            "zero_byte_flag": self.zero_byte_flag,
            "stat_device": self.stat_device,
            "stat_inode": self.stat_inode,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> CatalogFileObservation:
        return cls(
            relative_path=str(payload.get("relative_path") or ""),
            parent_relative_path=str(payload.get("parent_relative_path") or ""),
            file_name=str(payload.get("file_name") or ""),
            extension=str(payload["extension"]) if payload.get("extension") is not None else None,
            size_bytes=int(payload.get("size_bytes") or 0),
            created_at_fs=(
                str(payload["created_at_fs"])
                if payload.get("created_at_fs") is not None
                else None
            ),
            modified_at_fs=(
                str(payload["modified_at_fs"])
                if payload.get("modified_at_fs") is not None
                else None
            ),
            file_type_guess=str(payload.get("file_type_guess") or "unknown"),
            media_class_guess=str(payload.get("media_class_guess") or "unknown"),
            zero_byte_flag=bool(payload.get("zero_byte_flag")),
            stat_device=(
                str(payload["stat_device"]) if payload.get("stat_device") is not None else None
            ),
            stat_inode=(
                str(payload["stat_inode"]) if payload.get("stat_inode") is not None else None
            ),
        )
