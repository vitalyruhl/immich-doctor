import json

from typer.testing import CliRunner

from immich_doctor.cli.main import app


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
