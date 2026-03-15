from __future__ import annotations

import errno
from dataclasses import dataclass, field
from pathlib import Path

from immich_doctor.adapters.filesystem import FilesystemAdapter
from immich_doctor.adapters.media_probe import MediaProbeAdapter
from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.runtime.integrity.models import (
    FileIntegrityFinding,
    FileIntegrityInspectResult,
    FileIntegrityStatus,
    FileIntegritySummaryItem,
    FileRole,
    MediaKind,
)
from immich_doctor.runtime.metadata_failures.profile import (
    RUNTIME_METADATA_PROFILE_NAME,
    RuntimeMetadataProfileDetector,
    RuntimeMetadataProfileResult,
)

DEFAULT_BATCH_LIMIT = 100

IMAGE_EXTENSIONS = {
    ".jpg": {"jpeg"},
    ".jpeg": {"jpeg"},
    ".png": {"png"},
    ".webp": {"webp"},
    ".tif": {"tiff"},
    ".tiff": {"tiff"},
    ".bmp": {"bmp"},
    ".gif": {"gif"},
}
VIDEO_EXTENSIONS = {
    ".mp4": {"mp4", "mov"},
    ".mov": {"mov"},
    ".m4v": {"mp4", "mov"},
    ".m4a": {"mp4", "mov"},
    ".webm": {"webm", "matroska"},
    ".mkv": {"matroska"},
    ".avi": {"avi"},
}
AUDIO_EXTENSIONS = {
    ".mp3": {"mp3"},
    ".wav": {"wav"},
    ".flac": {"flac"},
    ".ogg": {"ogg"},
    ".aac": {"aac"},
    ".m4a": {"mp4", "mov"},
}


@dataclass(slots=True)
class RuntimeFileIntegrityAnalyzer:
    filesystem: FilesystemAdapter = field(default_factory=FilesystemAdapter)
    media_probe: MediaProbeAdapter = field(default_factory=MediaProbeAdapter)

    def inspect_records(
        self,
        asset_rows: list[dict[str, object]],
        asset_file_rows: dict[str, list[dict[str, object]]],
        *,
        include_derivatives: bool,
    ) -> list[FileIntegrityFinding]:
        findings: list[FileIntegrityFinding] = []
        for asset_row in asset_rows:
            asset_id = str(asset_row["id"])
            source_path = str(asset_row["originalPath"])
            source_media_kind = self._media_kind(str(asset_row["type"]), file_role=FileRole.SOURCE)
            findings.append(
                self._inspect_file(
                    asset_id=asset_id,
                    path=source_path,
                    media_kind=source_media_kind,
                    file_role=FileRole.SOURCE,
                )
            )

            if not include_derivatives:
                continue

            for file_row in asset_file_rows.get(asset_id, []):
                file_role = self._file_role(str(file_row["type"]))
                findings.append(
                    self._inspect_file(
                        asset_id=asset_id,
                        path=str(file_row["path"]),
                        media_kind=self._media_kind(str(asset_row["type"]), file_role=file_role),
                        file_role=file_role,
                        asset_file_id=str(file_row["id"]),
                    )
                )
        return findings

    def _inspect_file(
        self,
        *,
        asset_id: str,
        path: str,
        media_kind: MediaKind,
        file_role: FileRole,
        asset_file_id: str | None = None,
    ) -> FileIntegrityFinding:
        file_path = Path(path)
        extension = file_path.suffix.lower() or None
        finding_key = asset_file_id or file_path.name
        finding_id = f"file_integrity:{asset_id}:{file_role.value}:{finding_key}"

        try:
            stat_result = self.filesystem.stat_path(file_path)
        except FileNotFoundError:
            return self._build_finding(
                finding_id=finding_id,
                asset_id=asset_id,
                file_role=file_role,
                media_kind=media_kind,
                path=path,
                status=FileIntegrityStatus.FILE_MISSING,
                asset_file_id=asset_file_id,
                extension=extension,
                message="File path does not exist in the current runtime filesystem.",
            )
        except PermissionError:
            return self._build_finding(
                finding_id=finding_id,
                asset_id=asset_id,
                file_role=file_role,
                media_kind=media_kind,
                path=path,
                status=FileIntegrityStatus.FILE_PERMISSION_DENIED,
                asset_file_id=asset_file_id,
                extension=extension,
                message="File path exists but cannot be accessed due to permissions.",
            )
        except OSError as exc:
            return self._build_finding(
                finding_id=finding_id,
                asset_id=asset_id,
                file_role=file_role,
                media_kind=media_kind,
                path=path,
                status=FileIntegrityStatus.FILE_UNKNOWN_PROBLEM,
                asset_file_id=asset_file_id,
                extension=extension,
                message=f"File path could not be inspected: {exc.strerror or exc}.",
                details={"errno": exc.errno},
            )

        size_bytes = stat_result.st_size
        if size_bytes == 0:
            return self._build_finding(
                finding_id=finding_id,
                asset_id=asset_id,
                file_role=file_role,
                media_kind=media_kind,
                path=path,
                status=FileIntegrityStatus.FILE_EMPTY,
                asset_file_id=asset_file_id,
                extension=extension,
                size_bytes=size_bytes,
                message="File exists but is zero bytes.",
            )

        try:
            self.filesystem.read_probe(file_path)
        except PermissionError:
            return self._build_finding(
                finding_id=finding_id,
                asset_id=asset_id,
                file_role=file_role,
                media_kind=media_kind,
                path=path,
                status=FileIntegrityStatus.FILE_PERMISSION_DENIED,
                asset_file_id=asset_file_id,
                extension=extension,
                size_bytes=size_bytes,
                message="File exists but is not readable by the current process.",
            )
        except OSError as exc:
            status = (
                FileIntegrityStatus.FILE_PERMISSION_DENIED
                if exc.errno in {errno.EACCES, errno.EPERM}
                else FileIntegrityStatus.FILE_UNKNOWN_PROBLEM
            )
            return self._build_finding(
                finding_id=finding_id,
                asset_id=asset_id,
                file_role=file_role,
                media_kind=media_kind,
                path=path,
                status=status,
                asset_file_id=asset_file_id,
                extension=extension,
                size_bytes=size_bytes,
                message=f"File read probe failed: {exc.strerror or exc}.",
                details={"errno": exc.errno},
            )

        probe_result = self._probe_media(file_path, media_kind)
        if not probe_result.ok:
            return self._build_finding(
                finding_id=finding_id,
                asset_id=asset_id,
                file_role=file_role,
                media_kind=media_kind,
                path=path,
                status=self._map_probe_status(probe_result.error_category),
                asset_file_id=asset_file_id,
                extension=extension,
                size_bytes=size_bytes,
                detected_format=probe_result.detected_format,
                message=probe_result.error_message or "Media probe failed.",
                details={"probe_error_category": probe_result.error_category},
            )

        if (
            extension
            and probe_result.detected_format
            and self._is_type_mismatch(
                extension=extension,
                detected_format=probe_result.detected_format,
                media_kind=media_kind,
            )
        ):
            return self._build_finding(
                finding_id=finding_id,
                asset_id=asset_id,
                file_role=file_role,
                media_kind=media_kind,
                path=path,
                status=FileIntegrityStatus.FILE_TYPE_MISMATCH,
                asset_file_id=asset_file_id,
                extension=extension,
                size_bytes=size_bytes,
                detected_format=probe_result.detected_format,
                message="Detected media format does not match the file extension.",
            )

        return self._build_finding(
            finding_id=finding_id,
            asset_id=asset_id,
            file_role=file_role,
            media_kind=media_kind,
            path=path,
            status=FileIntegrityStatus.FILE_OK,
            asset_file_id=asset_file_id,
            extension=extension,
            size_bytes=size_bytes,
            detected_format=probe_result.detected_format,
            message="File passed the current physical integrity checks.",
        )

    def _probe_media(self, path: Path, media_kind: MediaKind):
        if media_kind == MediaKind.IMAGE:
            return self.media_probe.probe_image(path)
        if media_kind in {MediaKind.VIDEO, MediaKind.AUDIO}:
            return self.media_probe.probe_av(path)
        return self.media_probe.probe_unknown(path)

    def _map_probe_status(self, error_category: str | None) -> FileIntegrityStatus:
        mapping = {
            "missing_file": FileIntegrityStatus.FILE_MISSING,
            "permission_denied": FileIntegrityStatus.FILE_PERMISSION_DENIED,
            "truncated": FileIntegrityStatus.FILE_TRUNCATED,
            "container_broken": FileIntegrityStatus.FILE_CONTAINER_BROKEN,
            "corrupted": FileIntegrityStatus.FILE_CORRUPTED,
            "type_mismatch": FileIntegrityStatus.FILE_TYPE_MISMATCH,
            "unsupported_format": FileIntegrityStatus.FILE_TYPE_MISMATCH,
            "tool_missing": FileIntegrityStatus.FILE_UNKNOWN_PROBLEM,
            "runtime_tooling_error": FileIntegrityStatus.FILE_UNKNOWN_PROBLEM,
        }
        return mapping.get(error_category, FileIntegrityStatus.FILE_UNKNOWN_PROBLEM)

    def _is_type_mismatch(
        self,
        *,
        extension: str,
        detected_format: str,
        media_kind: MediaKind,
    ) -> bool:
        detected = {part.strip() for part in detected_format.split(",") if part.strip()}
        if media_kind == MediaKind.IMAGE:
            expected = IMAGE_EXTENSIONS.get(extension)
        elif media_kind == MediaKind.VIDEO:
            expected = VIDEO_EXTENSIONS.get(extension)
        elif media_kind == MediaKind.AUDIO:
            expected = AUDIO_EXTENSIONS.get(extension)
        else:
            expected = (
                IMAGE_EXTENSIONS.get(extension)
                or VIDEO_EXTENSIONS.get(extension)
                or AUDIO_EXTENSIONS.get(extension)
            )
        return bool(expected) and detected.isdisjoint(expected)

    def _build_finding(
        self,
        *,
        finding_id: str,
        asset_id: str,
        file_role: FileRole,
        media_kind: MediaKind,
        path: str,
        status: FileIntegrityStatus,
        asset_file_id: str | None,
        extension: str | None,
        message: str,
        size_bytes: int | None = None,
        detected_format: str | None = None,
        details: dict[str, object] | None = None,
    ) -> FileIntegrityFinding:
        return FileIntegrityFinding(
            finding_id=finding_id,
            asset_id=asset_id,
            file_role=file_role,
            media_kind=media_kind,
            path=path,
            status=status,
            asset_file_id=asset_file_id,
            message=message,
            size_bytes=size_bytes,
            detected_format=detected_format,
            extension=extension,
            details=dict(details or {}),
        )

    def _file_role(self, asset_file_type: str) -> FileRole:
        normalized = asset_file_type.lower()
        if normalized == "preview":
            return FileRole.PREVIEW
        if normalized == "thumbnail":
            return FileRole.THUMBNAIL
        return FileRole.DERIVATIVE

    def _media_kind(self, asset_type: str, *, file_role: FileRole) -> MediaKind:
        if file_role in {FileRole.PREVIEW, FileRole.THUMBNAIL}:
            return MediaKind.IMAGE
        normalized = asset_type.lower()
        if normalized == "image":
            return MediaKind.IMAGE
        if normalized == "video":
            return MediaKind.VIDEO
        if normalized == "audio":
            return MediaKind.AUDIO
        return MediaKind.UNKNOWN


@dataclass(slots=True)
class RuntimeIntegrityInspectService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    analyzer: RuntimeFileIntegrityAnalyzer = field(default_factory=RuntimeFileIntegrityAnalyzer)
    batch_limit: int = DEFAULT_BATCH_LIMIT

    def run(
        self,
        settings: AppSettings,
        *,
        limit: int | None = None,
        offset: int = 0,
        include_derivatives: bool = True,
    ) -> FileIntegrityInspectResult:
        dsn = settings.postgres_dsn_value()
        if not dsn:
            return FileIntegrityInspectResult(
                domain="runtime.integrity",
                action="inspect",
                summary=(
                    "Runtime integrity inspection failed because database access is not configured."
                ),
                checks=[
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database DSN is not configured.",
                    )
                ],
                findings=[],
                summary_items=[],
                metadata={"environment": settings.environment},
            )

        timeout = settings.postgres_connect_timeout_seconds
        connection_check = self.postgres.validate_connection(dsn, timeout)
        if connection_check.status == CheckStatus.FAIL:
            return FileIntegrityInspectResult(
                domain="runtime.integrity",
                action="inspect",
                summary=(
                    "Runtime integrity inspection failed because PostgreSQL could not be reached."
                ),
                checks=[connection_check],
                findings=[],
                summary_items=[],
                metadata={"environment": settings.environment},
            )

        profile_result = RuntimeMetadataProfileDetector(self.postgres).detect(dsn, timeout)
        checks = [connection_check, self._profile_check(profile_result)]
        if not profile_result.supported:
            return FileIntegrityInspectResult(
                domain="runtime.integrity",
                action="inspect",
                summary=(
                    "Runtime integrity inspection skipped because the current PostgreSQL schema is "
                    "unsupported."
                ),
                checks=checks,
                findings=[],
                summary_items=[],
                recommendations=[
                    "This workflow currently supports only the exact observed runtime metadata "
                    "profile.",
                ],
                metadata={"environment": settings.environment},
            )
        checks.append(self._ffprobe_check())

        batch_size = limit or self.batch_limit
        asset_rows = self.postgres.list_assets_for_runtime_integrity(
            dsn,
            timeout,
            limit=batch_size,
            offset=offset,
        )
        asset_files = self.postgres.list_asset_files_for_assets(
            dsn,
            timeout,
            asset_ids=tuple(str(row["id"]) for row in asset_rows),
        )
        asset_file_lookup: dict[str, list[dict[str, object]]] = {}
        for row in asset_files:
            asset_file_lookup.setdefault(str(row["assetId"]), []).append(row)

        findings = self.analyzer.inspect_records(
            asset_rows,
            asset_file_lookup,
            include_derivatives=include_derivatives,
        )
        summary_items = self._build_summary_items(findings)
        return FileIntegrityInspectResult(
            domain="runtime.integrity",
            action="inspect",
            summary=self._build_summary(findings, batch_size, offset),
            checks=checks,
            findings=findings,
            summary_items=summary_items,
            recommendations=self._recommendations(findings),
            metadata={
                "environment": settings.environment,
                "limit": batch_size,
                "offset": offset,
                "include_derivatives": include_derivatives,
            },
        )

    def _profile_check(self, profile_result: RuntimeMetadataProfileResult) -> CheckResult:
        if profile_result.supported:
            return CheckResult(
                name="runtime_metadata_schema_profile",
                status=CheckStatus.PASS,
                message=(
                    f"Supported schema profile `{profile_result.profile.name}` detected for "
                    "runtime integrity inspection."
                ),
            )
        return CheckResult(
            name="runtime_metadata_schema_profile",
            status=CheckStatus.SKIP,
            message=(
                f"Unsupported schema for `{RUNTIME_METADATA_PROFILE_NAME}`. Runtime integrity "
                "inspection will be skipped."
            ),
            details={
                "missing_tables": list(profile_result.missing_tables),
                "missing_columns": {
                    table: list(columns)
                    for table, columns in profile_result.missing_columns.items()
                },
            },
        )

    def _ffprobe_check(self) -> CheckResult:
        if self.analyzer.media_probe.ffprobe_available():
            return CheckResult(
                name="ffprobe_runtime_tool",
                status=CheckStatus.PASS,
                message="ffprobe is available for video and audio container probing.",
            )
        return CheckResult(
            name="ffprobe_runtime_tool",
            status=CheckStatus.WARN,
            message=(
                "ffprobe is not available. Video and audio corruption checks may degrade to "
                "unknown problem classifications."
            ),
        )

    def _build_summary_items(
        self,
        findings: list[FileIntegrityFinding],
    ) -> list[FileIntegritySummaryItem]:
        counts: dict[FileIntegrityStatus, int] = {}
        for finding in findings:
            counts[finding.status] = counts.get(finding.status, 0) + 1
        return [
            FileIntegritySummaryItem(status=status, count=counts[status])
            for status in FileIntegrityStatus
            if counts.get(status)
        ]

    def _build_summary(
        self,
        findings: list[FileIntegrityFinding],
        limit: int,
        offset: int,
    ) -> str:
        if not findings:
            return (
                f"Runtime integrity inspection found no files in the current batch "
                f"(limit={limit}, offset={offset})."
            )
        failed_count = sum(
            1 for finding in findings if finding.status != FileIntegrityStatus.FILE_OK
        )
        ok_count = len(findings) - failed_count
        return (
            f"Runtime integrity inspection checked {len(findings)} files. "
            f"{ok_count} passed and {failed_count} showed physical file defects or unknown "
            "problems."
        )

    def _recommendations(self, findings: list[FileIntegrityFinding]) -> list[str]:
        if not findings:
            return ["Increase --limit or adjust --offset to inspect additional files."]
        if any(
            finding.status == FileIntegrityStatus.FILE_PERMISSION_DENIED for finding in findings
        ):
            return [
                "Investigate file ownership and permissions before retrying metadata extraction."
            ]
        if any(finding.status != FileIntegrityStatus.FILE_OK for finding in findings):
            return [
                "Treat physical file defects as primary causes before diagnosing metadata jobs."
            ]
        return ["Physical files in this batch passed the current integrity checks."]
