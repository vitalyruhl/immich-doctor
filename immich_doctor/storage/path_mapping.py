from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from immich_doctor.core.config import AppSettings

_LEGACY_ROOT_PREFIX = PurePosixPath("/usr/src/app/upload")
_LEGACY_SEGMENTS_BY_ROOT = {
    "library": "library",
    "uploads": "upload",
    "thumbs": "thumbs",
    "profile": "profile",
    "video": "encoded-video",
}


@dataclass(frozen=True, slots=True)
class ResolvedStoragePath:
    root_slug: str
    relative_path: str
    absolute_path: Path
    mapping_mode: str


@dataclass(frozen=True, slots=True)
class _RootMapping:
    slug: str
    root_path: Path
    runtime_prefix: PurePosixPath
    legacy_prefix: PurePosixPath | None


class ImmichStoragePathResolver:
    def __init__(self, settings: AppSettings) -> None:
        self._roots = self._build_roots(settings)

    def resolve(self, path_text: str) -> ResolvedStoragePath | None:
        normalized = self._normalize(path_text)
        if normalized is None:
            return None

        for root in self._roots:
            relative = self._relative_to(normalized, root.runtime_prefix)
            if relative is not None:
                return ResolvedStoragePath(
                    root_slug=root.slug,
                    relative_path=relative,
                    absolute_path=self._join_root(root.root_path, relative),
                    mapping_mode="runtime",
                )

        for root in self._roots:
            if root.legacy_prefix is None:
                continue
            relative = self._relative_to(normalized, root.legacy_prefix)
            if relative is not None:
                return ResolvedStoragePath(
                    root_slug=root.slug,
                    relative_path=relative,
                    absolute_path=self._join_root(root.root_path, relative),
                    mapping_mode="legacy",
                )
        return None

    def looks_like_legacy_immich_path(self, path_text: str) -> bool:
        normalized = self._normalize(path_text)
        return (
            normalized is not None
            and self._relative_to(normalized, _LEGACY_ROOT_PREFIX) is not None
        )

    def _build_roots(self, settings: AppSettings) -> tuple[_RootMapping, ...]:
        roots: list[_RootMapping] = []
        configured = (
            ("library", settings.immich_library_root),
            ("uploads", settings.immich_uploads_path),
            ("thumbs", settings.immich_thumbs_path),
            ("profile", settings.immich_profile_path),
            ("video", settings.immich_video_path),
        )
        for slug, path in configured:
            if path is None:
                continue
            roots.append(
                _RootMapping(
                    slug=slug,
                    root_path=path,
                    runtime_prefix=PurePosixPath(str(path).replace("\\", "/")),
                    legacy_prefix=(
                        _LEGACY_ROOT_PREFIX / _LEGACY_SEGMENTS_BY_ROOT[slug]
                        if slug in _LEGACY_SEGMENTS_BY_ROOT
                        else None
                    ),
                )
            )
        return tuple(roots)

    def _normalize(self, path_text: str) -> PurePosixPath | None:
        value = path_text.strip()
        if not value:
            return None
        return PurePosixPath(value.replace("\\", "/"))

    def _relative_to(
        self,
        path: PurePosixPath,
        prefix: PurePosixPath,
    ) -> str | None:
        try:
            relative = path.relative_to(prefix)
        except ValueError:
            return None
        parts = [part for part in relative.parts if part not in {"", "."}]
        if not parts:
            return ""
        return PurePosixPath(*parts).as_posix()

    def _join_root(self, root_path: Path, relative_path: str) -> Path:
        if not relative_path:
            return root_path
        return root_path.joinpath(*PurePosixPath(relative_path).parts)
