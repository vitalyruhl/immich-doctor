from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.runtime.integrity.models import FileIntegrityStatus
from immich_doctor.runtime.integrity.service import (
    RuntimeFileIntegrityAnalyzer,
    RuntimeIntegrityInspectService,
)


@dataclass(slots=True)
class _FakeStat:
    st_size: int


def _normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


class _FakeFilesystem:
    def __init__(self, states: dict[str, tuple[str, int | None]]) -> None:
        self.states = states

    def stat_path(self, path: Path) -> _FakeStat:
        state, size = self.states[_normalize_path(path)]
        if state == "missing":
            raise FileNotFoundError(str(path))
        if state == "denied":
            raise PermissionError(str(path))
        return _FakeStat(st_size=int(size or 0))

    def read_probe(self, path: Path, size: int = 8192) -> bytes:
        state, _ = self.states[_normalize_path(path)]
        if state == "read_denied":
            raise PermissionError(str(path))
        return b"probe"


class _FakeMediaProbe:
    def __init__(
        self,
        *,
        ffprobe_available: bool,
        image_formats: dict[str, str | None],
    ) -> None:
        self._ffprobe_available = ffprobe_available
        self.image_formats = image_formats

    def ffprobe_available(self) -> bool:
        return self._ffprobe_available

    def probe_image(self, path: Path):
        return _ProbeResult(ok=True, detected_format=self.image_formats.get(_normalize_path(path)))

    def probe_av(self, path: Path):
        return _ProbeResult(ok=True, detected_format="mp4")

    def probe_unknown(self, path: Path):
        return _ProbeResult(ok=True, detected_format=None)


@dataclass(slots=True)
class _ProbeResult:
    ok: bool
    detected_format: str | None = None
    error_category: str | None = None
    error_message: str | None = None


class _FakePostgres:
    def __init__(self, *, assets: list[dict[str, object]], supported: bool = True) -> None:
        self.assets = assets
        self.supported = supported

    def validate_connection(self, dsn: str, timeout_seconds: int) -> CheckResult:
        return CheckResult(
            name="postgres_connection",
            status=CheckStatus.PASS,
            message="PostgreSQL connection established.",
        )

    def list_tables(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        tables = [
            {"table_schema": "public", "table_name": "asset"},
            {"table_schema": "public", "table_name": "asset_file"},
        ]
        if self.supported:
            tables.append({"table_schema": "public", "table_name": "asset_job_status"})
        return tables

    def list_columns(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
    ) -> list[dict[str, object]]:
        columns = {
            "asset": ("id", "type", "originalPath"),
            "asset_file": ("id", "assetId", "type", "path"),
            "asset_job_status": ("assetId", "metadataExtractedAt"),
        }
        return [{"column_name": name} for name in columns.get(table_name, ())]

    def list_assets_for_runtime_integrity(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, object]]:
        return self.assets[offset : offset + limit]

    def list_asset_files_for_assets(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        asset_ids: tuple[str, ...],
    ) -> list[dict[str, object]]:
        return []


def test_runtime_integrity_service_reports_file_states() -> None:
    assets = [
        {"id": "asset-missing", "type": "image", "originalPath": "C:/library/missing.jpg"},
        {"id": "asset-empty", "type": "image", "originalPath": "C:/library/empty.jpg"},
        {"id": "asset-mismatch", "type": "image", "originalPath": "C:/library/mismatch.png"},
        {"id": "asset-ok", "type": "image", "originalPath": "C:/library/ok.jpg"},
    ]
    analyzer = RuntimeFileIntegrityAnalyzer(
        filesystem=_FakeFilesystem(
            {
                "C:/library/missing.jpg": ("missing", None),
                "C:/library/empty.jpg": ("ok", 0),
                "C:/library/mismatch.png": ("ok", 128),
                "C:/library/ok.jpg": ("ok", 256),
            }
        ),
        media_probe=_FakeMediaProbe(
            ffprobe_available=False,
            image_formats={
                "C:/library/mismatch.png": "jpeg",
                "C:/library/ok.jpg": "jpeg",
            },
        ),
    )
    service = RuntimeIntegrityInspectService(
        postgres=_FakePostgres(assets=assets),
        analyzer=analyzer,
    )

    result = service.run(
        AppSettings(
            db_host="postgres",
            db_name="immich",
            db_user="immich",
            db_password="secret",
        )
    )

    findings_by_asset = {finding.asset_id: finding for finding in result.findings}

    assert result.overall_status == CheckStatus.FAIL
    assert findings_by_asset["asset-missing"].status == FileIntegrityStatus.FILE_MISSING
    assert findings_by_asset["asset-empty"].status == FileIntegrityStatus.FILE_EMPTY
    assert findings_by_asset["asset-mismatch"].status == FileIntegrityStatus.FILE_TYPE_MISMATCH
    assert findings_by_asset["asset-ok"].status == FileIntegrityStatus.FILE_OK
    assert any(
        check.name == "ffprobe_runtime_tool" and check.status == CheckStatus.WARN
        for check in result.checks
    )


def test_runtime_integrity_service_skips_unsupported_schema() -> None:
    service = RuntimeIntegrityInspectService(
        postgres=_FakePostgres(assets=[], supported=False),
        analyzer=RuntimeFileIntegrityAnalyzer(
            filesystem=_FakeFilesystem({}),
            media_probe=_FakeMediaProbe(ffprobe_available=False, image_formats={}),
        ),
    )

    result = service.run(
        AppSettings(
            db_host="postgres",
            db_name="immich",
            db_user="immich",
            db_password="secret",
        )
    )

    assert result.overall_status == CheckStatus.SKIP
    assert result.findings == []
    assert "unsupported" in result.summary.lower()
