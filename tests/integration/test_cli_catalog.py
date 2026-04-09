import json

from typer.testing import CliRunner

from immich_doctor.cli.main import app
from immich_doctor.core.models import CheckStatus, ValidationReport, ValidationSection


def test_analyze_catalog_scan_and_zero_byte_json_output(tmp_path, monkeypatch) -> None:
    runner = CliRunner()

    uploads = tmp_path / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    (uploads / "empty.jpg").write_bytes(b"")
    (uploads / "asset.txt").write_bytes(b"hello")

    manifests = tmp_path / "manifests"
    reports = tmp_path / "reports"
    quarantine = tmp_path / "quarantine"
    logs = tmp_path / "logs"
    tmp_dir = tmp_path / "tmp"
    for path in [manifests, reports, quarantine, logs, tmp_dir]:
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("IMMICH_UPLOADS_PATH", str(uploads))
    monkeypatch.setenv("MANIFESTS_PATH", str(manifests))
    monkeypatch.setenv("REPORTS_PATH", str(reports))
    monkeypatch.setenv("QUARANTINE_PATH", str(quarantine))
    monkeypatch.setenv("LOG_PATH", str(logs))
    monkeypatch.setenv("TMP_PATH", str(tmp_dir))

    scan_result = runner.invoke(
        app,
        ["analyze", "catalog", "scan", "--root", "uploads", "--output", "json"],
    )

    assert scan_result.exit_code == 0
    scan_payload = json.loads(scan_result.stdout)
    assert scan_payload["domain"] == "analyze.catalog"
    assert scan_payload["action"] == "scan"
    assert scan_payload["status"] == "PASS"

    zero_result = runner.invoke(
        app,
        ["analyze", "catalog", "zero-byte", "--root", "uploads", "--output", "json"],
    )

    assert zero_result.exit_code == 1
    zero_payload = json.loads(zero_result.stdout)
    assert zero_payload["domain"] == "analyze.catalog"
    assert zero_payload["action"] == "zero-byte"
    assert zero_payload["sections"][0]["rows"][0]["relative_path"] == "empty.jpg"


def test_analyze_catalog_consistency_json_output(monkeypatch) -> None:
    runner = CliRunner()

    def fake_run(self, settings):
        del self, settings
        return ValidationReport(
            domain="consistency.catalog",
            action="validate",
            summary="Catalog consistency found mismatches.",
            checks=[],
            sections=[
                ValidationSection(
                    name="DB_ORIGINALS_MISSING_ON_STORAGE",
                    status=CheckStatus.FAIL,
                    rows=[{"asset_id": "asset-1", "relative_path": "user-a/missing.jpg"}],
                )
            ],
            metadata={"totals": {"dbOriginalsMissingOnStorage": 1}},
        )

    monkeypatch.setattr(
        "immich_doctor.cli.analyze.CatalogConsistencyValidationService.run",
        fake_run,
    )

    result = runner.invoke(app, ["analyze", "catalog", "consistency", "--output", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["domain"] == "consistency.catalog"
    assert payload["sections"][0]["rows"][0]["asset_id"] == "asset-1"
