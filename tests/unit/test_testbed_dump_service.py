from __future__ import annotations

import subprocess
from pathlib import Path

from immich_doctor.core.config import AppSettings
from immich_doctor.services.testbed_dump_service import (
    TestbedDumpImportService,
    TestbedDumpServiceError,
)


def _settings(tmp_path: Path, **overrides: object) -> AppSettings:
    defaults: dict[str, object] = {
        "_env_file": None,
        "environment": "dev-testbed",
        "db_host": "postgres",
        "db_port": 5432,
        "db_name": "immich",
        "db_user": "postgres",
        "db_password": "secret",
        "manifests_path": tmp_path / "manifests",
        "reports_path": tmp_path / "reports",
        "quarantine_path": tmp_path / "quarantine",
        "logs_path": tmp_path / "logs",
        "tmp_path": tmp_path / "tmp",
    }
    defaults.update(overrides)
    return AppSettings(**defaults)


def test_get_overview_reports_testbed_only_capability(tmp_path: Path) -> None:
    overview = TestbedDumpImportService().get_overview(
        _settings(tmp_path, environment="development")
    )

    assert overview.enabled is False
    assert overview.can_import is False
    assert "dev-testbed" in overview.summary


def test_resolve_dump_path_maps_host_path_into_container_mount(tmp_path: Path) -> None:
    dump_dir = tmp_path / "mounted-dumps"
    dump_dir.mkdir()
    dump_file = dump_dir / "immich.dump.sql"
    dump_file.write_text("-- test", encoding="utf-8")

    settings = _settings(
        tmp_path,
        testbed_dump_path=r"C:\Temp\immich-testdata\db\full\immich.dump.sql",
        testbed_dump_mount_source=r"C:\Temp\immich-testdata\db\full",
        testbed_container_dump_dir=dump_dir,
    )

    resolved = TestbedDumpImportService().resolve_dump_path(settings)

    assert resolved == dump_file


def test_import_dump_requires_force_for_non_empty_database(tmp_path: Path, monkeypatch) -> None:
    service = TestbedDumpImportService()
    dump_file = tmp_path / "immich.sql"
    dump_file.write_text("-- test", encoding="utf-8")
    settings = _settings(tmp_path, testbed_dump_path=str(dump_file))

    monkeypatch.setattr(TestbedDumpImportService, "database_is_empty", lambda self, settings: False)

    try:
        service.import_dump(settings, force=False)
    except TestbedDumpServiceError as exc:
        assert "without explicit force" in str(exc)
    else:  # pragma: no cover - explicit failure branch
        raise AssertionError("expected TestbedDumpServiceError for non-empty DB")


def test_maybe_auto_initialize_imports_dump_for_empty_testbed(tmp_path: Path, monkeypatch) -> None:
    service = TestbedDumpImportService()
    settings = _settings(
        tmp_path,
        testbed_dump_path=str(tmp_path / "immich.sql"),
        testbed_auto_import_on_empty=True,
        testbed_init_mode="FROM_DUMP",
    )
    calls: list[tuple[str | None, bool]] = []

    def fake_import_dump(self, settings_arg, *, requested_path=None, dump_format=None, force=False):
        del self, settings_arg, dump_format
        calls.append((requested_path, force))
        return {"classification": "success"}

    monkeypatch.setattr(TestbedDumpImportService, "database_is_empty", lambda self, settings: True)
    monkeypatch.setattr(TestbedDumpImportService, "import_dump", fake_import_dump)

    result = service.maybe_auto_initialize(settings)

    assert result == {"classification": "success"}
    assert calls == [(None, False)]


def test_maybe_auto_initialize_skips_non_empty_database(tmp_path: Path, monkeypatch) -> None:
    service = TestbedDumpImportService()
    settings = _settings(
        tmp_path,
        testbed_dump_path=str(tmp_path / "immich.sql"),
        testbed_auto_import_on_empty=True,
        testbed_init_mode="FROM_DUMP",
    )

    monkeypatch.setattr(TestbedDumpImportService, "database_is_empty", lambda self, settings: False)

    def fail_import(*args, **kwargs):
        raise AssertionError("import_dump should not run for a non-empty database")

    monkeypatch.setattr(TestbedDumpImportService, "import_dump", fail_import)

    assert service.maybe_auto_initialize(settings) is None


def test_restore_dump_reports_partial_success_for_replay_errors(
    tmp_path: Path, monkeypatch
) -> None:
    service = TestbedDumpImportService()
    dump_file = tmp_path / "immich.sql"
    dump_file.write_text("SELECT 1;\n", encoding="utf-8")
    settings = _settings(tmp_path)

    monkeypatch.setattr(
        TestbedDumpImportService,
        "_recreate_database",
        lambda self, **kwargs: None,
    )
    monkeypatch.setattr(
        TestbedDumpImportService,
        "_is_plain_sql_cluster_dump",
        lambda self, path: False,
    )
    monkeypatch.setattr(
        TestbedDumpImportService,
        "_run_command",
        lambda self, args, env: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="ERROR: insert or update violates foreign key constraint",
            stderr="",
        ),
    )
    monkeypatch.setattr(TestbedDumpImportService, "_database_exists", lambda self, **kwargs: True)

    result = service._restore_dump(
        settings,
        dsn=settings.postgres_dsn_value() or "",
        dump_path=dump_file,
        requested_path=str(dump_file),
        dump_format="plain",
        db_was_empty=True,
    )

    assert result.classification == "partial success"
    assert result.state.value == "partial"
    assert result.meaningful_error_count == 1
