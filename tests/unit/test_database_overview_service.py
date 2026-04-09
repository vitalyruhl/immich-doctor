from __future__ import annotations

from dataclasses import dataclass

from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport
from immich_doctor.services.database_overview import DatabaseOverviewService


@dataclass(slots=True)
class _FakeDbHealth:
    report: ValidationReport

    def run(self, settings: AppSettings) -> ValidationReport:
        return self.report


@dataclass(slots=True)
class _FakeSchemaDetector:
    payload: dict[str, object]

    class _State:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def to_dict(self) -> dict[str, object]:
            return self.payload

    def detect(self, dsn: str, timeout_seconds: int) -> _State:
        return self._State(self.payload)


@dataclass(slots=True)
class _FakePostgres:
    version_payload: dict[str, str]

    def fetch_server_version(self, dsn: str, timeout_seconds: int) -> dict[str, str]:
        return self.version_payload


@dataclass(slots=True)
class _FakeCatalogWorkflow:
    payload: dict[str, object]

    def get_consistency_job(self, settings: AppSettings) -> dict[str, object]:
        return self.payload


def test_database_overview_service_reports_supported_tested_version() -> None:
    service = DatabaseOverviewService(
        db_health=_FakeDbHealth(
            ValidationReport(
                domain="db.health",
                action="check",
                summary="Database health checks completed.",
                checks=[
                    CheckResult("postgres_host_resolution", CheckStatus.PASS, "Resolved."),
                    CheckResult("postgres_tcp_connection", CheckStatus.PASS, "Connected."),
                    CheckResult("postgres_connection", CheckStatus.PASS, "Login worked."),
                    CheckResult(
                        "postgres_round_trip_query", CheckStatus.PASS, "Round trip worked."
                    ),
                ],
            )
        ),
        postgres=_FakePostgres(
            {
                "server_version": "14.10",
                "server_version_num": "140010",
                "full_version": "PostgreSQL 14.10",
            }
        ),
        schema_detector=_FakeSchemaDetector(
            {
                "product_version_current": "2.5.6",
                "product_version_confidence": "high",
                "product_version_source": "version_history",
                "support_status": "supported",
                "schema_generation_key": "immich_schema:key",
                "risk_flags": [],
                "notes": [],
            }
        ),
        catalog_workflow=_FakeCatalogWorkflow(
            {
                "state": "completed",
                "summary": "Catalog consistency validation completed.",
                "result": {"report": {"summary": "ready"}},
            }
        ),
    )

    overview = service.run(
        AppSettings(
            db_host="postgres",
            db_name="immich",
            db_user="postgres",
            db_password="secret",
        )
    )

    assert overview["connectivity"]["status"] == "ok"
    assert overview["immich"]["productVersionCurrent"] == "2.5.6"
    assert overview["compatibility"]["status"] == "ok"
    assert overview["testedAgainstImmichVersion"] == "2.5.6"


def test_database_overview_service_marks_related_findings_as_waiting_during_indexing() -> None:
    service = DatabaseOverviewService(
        db_health=_FakeDbHealth(
            ValidationReport(
                domain="db.health",
                action="check",
                summary="Database health checks completed.",
                checks=[
                    CheckResult("postgres_host_resolution", CheckStatus.PASS, "Resolved."),
                    CheckResult("postgres_tcp_connection", CheckStatus.PASS, "Connected."),
                    CheckResult("postgres_connection", CheckStatus.PASS, "Login worked."),
                    CheckResult(
                        "postgres_round_trip_query", CheckStatus.PASS, "Round trip worked."
                    ),
                ],
            )
        ),
        postgres=_FakePostgres(
            {
                "server_version": "14.10",
                "server_version_num": "140010",
                "full_version": "PostgreSQL 14.10",
            }
        ),
        schema_detector=_FakeSchemaDetector(
            {
                "product_version_current": "2.5.5",
                "product_version_confidence": "high",
                "product_version_source": "version_history",
                "support_status": "supported",
                "schema_generation_key": "immich_schema:key",
                "risk_flags": [],
                "notes": [],
            }
        ),
        catalog_workflow=_FakeCatalogWorkflow(
            {
                "state": "pending",
                "summary": (
                    "Catalog consistency validation is waiting for the "
                    "catalog scan to finish."
                ),
                "result": {
                    "blockedBy": {
                        "jobType": "catalog_inventory_scan",
                        "summary": "Catalog scan running for root `uploads` (1/4).",
                    }
                },
            }
        ),
    )

    overview = service.run(
        AppSettings(
            db_host="postgres",
            db_name="immich",
            db_user="postgres",
            db_password="secret",
        )
    )

    assert overview["compatibility"]["status"] == "warning"
    assert overview["relatedFindings"]["status"] == "warning"
    assert "waiting for the active storage index scan" in overview["relatedFindings"]["summary"]
