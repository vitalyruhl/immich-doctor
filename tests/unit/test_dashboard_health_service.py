from __future__ import annotations

from dataclasses import dataclass

from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport
from immich_doctor.services.dashboard_health import DashboardHealthService, DashboardHealthStatus


@dataclass(slots=True)
class _FakeValidationService:
    report: ValidationReport

    def run(self, settings: AppSettings) -> ValidationReport:
        return self.report


def test_dashboard_health_service_reports_unknown_when_not_configured() -> None:
    service = DashboardHealthService()

    overview = service.run(AppSettings())
    items = {item.id: item for item in overview.items}

    assert overview.overall_status == DashboardHealthStatus.UNKNOWN
    assert items["immich-configured"].status == DashboardHealthStatus.UNKNOWN
    assert items["immich-reachable"].status == DashboardHealthStatus.UNKNOWN
    assert items["db-reachability"].status == DashboardHealthStatus.UNKNOWN
    assert items["storage-reachability"].status == DashboardHealthStatus.UNKNOWN
    assert items["consistency-readiness"].status == DashboardHealthStatus.UNKNOWN
    assert items["path-readiness"].status == DashboardHealthStatus.UNKNOWN
    assert items["backup-readiness"].status == DashboardHealthStatus.UNKNOWN
    assert items["scheduler-runtime-readiness"].status == DashboardHealthStatus.UNKNOWN


def test_dashboard_health_service_uses_real_checks_when_available(tmp_path) -> None:
    library_root = tmp_path / "library"
    uploads = library_root / "upload"
    thumbs = library_root / "thumbs"
    profile = library_root / "profile"
    video = library_root / "encoded-video"
    backup = tmp_path / "backup"

    for path in (library_root, uploads, thumbs, profile, video, backup):
        path.mkdir(parents=True, exist_ok=True)

    service = DashboardHealthService(
        db_health=_FakeValidationService(
            ValidationReport(
                domain="db.health",
                action="check",
                summary="Database health checks completed.",
                checks=[
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.PASS,
                        message="PostgreSQL connection established.",
                    )
                ],
            )
        ),
        runtime_validation=_FakeValidationService(
            ValidationReport(
                domain="runtime",
                action="validate",
                summary="Runtime validation completed.",
                checks=[
                    CheckResult(
                        name="runtime_identity",
                        status=CheckStatus.PASS,
                        message="Runtime identity information collected.",
                    )
                ],
            )
        ),
        backup_verify=_FakeValidationService(
            ValidationReport(
                domain="backup",
                action="verify",
                summary=(
                    "Backup verification completed for current target-readiness "
                    "and snapshot-manifest checks."
                ),
                checks=[
                    CheckResult(
                        name="backup_target_configured",
                        status=CheckStatus.PASS,
                        message="Backup target path is configured.",
                    ),
                    CheckResult(
                        name="backup_target_path",
                        status=CheckStatus.PASS,
                        message="Configured directory exists.",
                    ),
                ],
            )
        ),
    )

    overview = service.run(
        AppSettings(
            immich_library_root=library_root,
            immich_uploads_path=uploads,
            immich_thumbs_path=thumbs,
            immich_profile_path=profile,
            immich_video_path=video,
            backup_target_path=backup,
            db_host="postgres",
            db_name="immich",
            db_user="immich",
            db_password="secret",
        )
    )
    items = {item.id: item for item in overview.items}

    assert items["db-reachability"].status == DashboardHealthStatus.OK
    assert items["storage-reachability"].status == DashboardHealthStatus.OK
    assert items["consistency-readiness"].status == DashboardHealthStatus.UNKNOWN
    assert items["path-readiness"].status == DashboardHealthStatus.OK
    assert items["backup-readiness"].status == DashboardHealthStatus.OK
    assert items["scheduler-runtime-readiness"].status == DashboardHealthStatus.UNKNOWN
    assert overview.overall_status == DashboardHealthStatus.UNKNOWN


def test_dashboard_health_service_flags_path_problems(tmp_path) -> None:
    library_root = tmp_path / "library"
    uploads = tmp_path / "outside-upload"
    library_root.mkdir(parents=True, exist_ok=True)
    uploads.mkdir(parents=True, exist_ok=True)

    service = DashboardHealthService()

    overview = service.run(
        AppSettings(
            immich_library_root=library_root,
            immich_uploads_path=uploads,
        )
    )
    items = {item.id: item for item in overview.items}

    assert items["consistency-readiness"].status == DashboardHealthStatus.UNKNOWN
    assert items["path-readiness"].status == DashboardHealthStatus.ERROR
    assert "outside immich_library_root" in items["path-readiness"].details


def test_dashboard_health_service_reports_consistency_waiting_on_scan() -> None:
    class _FakeCatalogWorkflow:
        def get_consistency_job(self, settings: AppSettings) -> dict[str, object]:
            return {
                "jobId": None,
                "jobType": "catalog_consistency_validation",
                "state": "pending",
                "summary": (
                    "Catalog consistency validation is waiting for the catalog scan to finish."
                ),
                "result": {
                    "blockedBy": {
                        "jobId": "scan-1",
                        "jobType": "catalog_inventory_scan",
                        "state": "running",
                        "summary": "Catalog scan running for root `uploads` (1/4).",
                    }
                },
            }

    overview = DashboardHealthService(catalog_workflow=_FakeCatalogWorkflow()).run(AppSettings())
    items = {item.id: item for item in overview.items}

    assert items["consistency-readiness"].status == DashboardHealthStatus.WARNING
    assert "waiting for the active storage index scan" in items["consistency-readiness"].summary
