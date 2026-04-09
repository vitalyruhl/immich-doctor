from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.catalog.workflow_service import CatalogWorkflowService
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckStatus
from immich_doctor.db.health.service import DbHealthCheckService
from immich_doctor.db.schema_detection import DatabaseSchemaSupportStatus, DatabaseStateDetector
from immich_doctor.services.dashboard_health import DashboardHealthStatus

SUPPORTED_IMMICH_TEST_VERSION = "2.5.6"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class DatabaseOverviewService:
    db_health: DbHealthCheckService = field(default_factory=DbHealthCheckService)
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)
    schema_detector: DatabaseStateDetector = field(default_factory=DatabaseStateDetector)
    catalog_workflow: CatalogWorkflowService | None = None

    def run(self, settings: AppSettings) -> dict[str, object]:
        generated_at = _iso_now()
        host, port = settings.postgres_target()
        dsn = settings.postgres_dsn_value()
        database_name = self._database_name(settings, dsn)

        db_report = self.db_health.run(settings)
        checks_by_name = {check.name: check for check in db_report.checks}
        connection_check = checks_by_name.get("postgres_connection")
        query_check = checks_by_name.get("postgres_round_trip_query")
        access_ok = (
            connection_check is not None
            and connection_check.status == CheckStatus.PASS
            and query_check is not None
            and query_check.status == CheckStatus.PASS
        )
        connectivity_status = self._map_db_report_status(db_report)

        connectivity = {
            "status": connectivity_status.value,
            "summary": self._connectivity_summary(
                status=connectivity_status,
                access_ok=access_ok,
                host=host,
                port=port,
            ),
            "details": self._connectivity_details(db_report, status=connectivity_status),
            "host": host,
            "port": port,
            "databaseName": database_name,
            "accessWorks": access_ok,
            "error": None if access_ok else self._first_failing_message(db_report),
            "engine": "PostgreSQL" if dsn else None,
        }

        server_version: dict[str, str] | None = None
        server_version_error: str | None = None
        database_state: dict[str, object] | None = None
        database_state_error: str | None = None

        if dsn is not None and access_ok:
            try:
                server_version = self.postgres.fetch_server_version(
                    dsn,
                    settings.postgres_connect_timeout_seconds,
                )
            except Exception as exc:
                server_version_error = str(exc)
            try:
                database_state = self.schema_detector.detect(
                    dsn,
                    settings.postgres_connect_timeout_seconds,
                ).to_dict()
            except Exception as exc:
                database_state_error = str(exc)

        immich = self._immich_section(
            database_state=database_state,
            detection_error=database_state_error,
        )
        compatibility = self._compatibility_section(
            connectivity_status=connectivity_status,
            database_state=database_state,
        )
        related_findings = self._related_findings(settings)

        return {
            "generatedAt": generated_at,
            "connectivity": {
                **connectivity,
                "serverVersion": server_version["server_version"]
                if server_version is not None
                else None,
                "serverVersionNum": server_version["server_version_num"]
                if server_version is not None
                else None,
                "serverVersionRaw": server_version["full_version"]
                if server_version is not None
                else None,
                "serverVersionError": server_version_error,
            },
            "immich": immich,
            "compatibility": compatibility,
            "relatedFindings": related_findings,
            "testedAgainstImmichVersion": SUPPORTED_IMMICH_TEST_VERSION,
        }

    def _database_name(self, settings: AppSettings, dsn: str | None) -> str | None:
        if settings.db_name:
            return settings.db_name
        if dsn is None:
            return None
        parsed = urlparse(dsn)
        if parsed.path and parsed.path != "/":
            return parsed.path.removeprefix("/")
        return None

    def _map_db_report_status(
        self,
        report,
    ) -> DashboardHealthStatus:
        if report.overall_status == CheckStatus.FAIL:
            failing_names = {
                check.name for check in report.checks if check.status == CheckStatus.FAIL
            }
            if failing_names <= {"postgres_connection", "postgres_round_trip_query"}:
                return DashboardHealthStatus.WARNING
            return DashboardHealthStatus.ERROR
        if report.overall_status == CheckStatus.WARN:
            return DashboardHealthStatus.WARNING
        if report.overall_status == CheckStatus.PASS:
            return DashboardHealthStatus.OK
        return DashboardHealthStatus.UNKNOWN

    def _connectivity_summary(
        self,
        *,
        status: DashboardHealthStatus,
        access_ok: bool,
        host: str | None,
        port: int | None,
    ) -> str:
        if access_ok and host is not None and port is not None:
            return f"Database access works against {host}:{port}."
        if status == DashboardHealthStatus.WARNING:
            return (
                "Database target is reachable, but authenticated access is not fully working yet."
            )
        if status == DashboardHealthStatus.ERROR:
            return "Database target cannot be reached reliably."
        return "Database access cannot be verified yet."

    def _connectivity_details(self, report, *, status: DashboardHealthStatus) -> str:
        failing_messages = [
            check.message for check in report.checks if check.status != CheckStatus.PASS
        ]
        if failing_messages:
            return " ".join(failing_messages)
        if status == DashboardHealthStatus.OK:
            return (
                "Host resolution, TCP reachability, PostgreSQL login, and round-trip query passed."
            )
        return report.summary

    def _first_failing_message(self, report) -> str | None:
        for check in report.checks:
            if check.status != CheckStatus.PASS:
                return check.message
        return None

    def _immich_section(
        self,
        *,
        database_state: dict[str, object] | None,
        detection_error: str | None,
    ) -> dict[str, object]:
        if database_state is None:
            return {
                "status": DashboardHealthStatus.UNKNOWN.value,
                "summary": "Immich version and schema support are not available yet.",
                "details": detection_error
                or "This requires a successful PostgreSQL connection and readable schema metadata.",
                "productVersionCurrent": None,
                "productVersionConfidence": "unknown",
                "productVersionSource": "unknown",
                "supportStatus": "unknown",
                "schemaGenerationKey": None,
                "riskFlags": [],
                "notes": [],
            }

        support_status = str(database_state.get("support_status") or "unknown")
        product_version = database_state.get("product_version_current")
        return {
            "status": self._support_status_to_health_status(support_status).value,
            "summary": (
                f"Detected Immich schema profile {support_status}."
                if product_version is None
                else f"Detected Immich {product_version} with schema profile {support_status}."
            ),
            "details": self._immich_details(database_state),
            "productVersionCurrent": product_version,
            "productVersionConfidence": database_state.get("product_version_confidence")
            or "unknown",
            "productVersionSource": database_state.get("product_version_source") or "unknown",
            "supportStatus": support_status,
            "schemaGenerationKey": database_state.get("schema_generation_key"),
            "riskFlags": database_state.get("risk_flags") or [],
            "notes": database_state.get("notes") or [],
        }

    def _support_status_to_health_status(self, support_status: str) -> DashboardHealthStatus:
        if support_status == DatabaseSchemaSupportStatus.SUPPORTED.value:
            return DashboardHealthStatus.OK
        if support_status in {
            DatabaseSchemaSupportStatus.DRIFTED.value,
            DatabaseSchemaSupportStatus.PARTIAL_MIGRATION.value,
        }:
            return DashboardHealthStatus.WARNING
        if support_status == DatabaseSchemaSupportStatus.UNSUPPORTED.value:
            return DashboardHealthStatus.ERROR
        return DashboardHealthStatus.UNKNOWN

    def _immich_details(self, database_state: dict[str, object]) -> str:
        source = database_state.get("product_version_source") or "unknown"
        confidence = database_state.get("product_version_confidence") or "unknown"
        version = database_state.get("product_version_current") or "unknown"
        return f"Immich version signal: {version} (source: {source}, confidence: {confidence})."

    def _compatibility_section(
        self,
        *,
        connectivity_status: DashboardHealthStatus,
        database_state: dict[str, object] | None,
    ) -> dict[str, object]:
        if connectivity_status == DashboardHealthStatus.ERROR:
            return {
                "status": DashboardHealthStatus.ERROR.value,
                "summary": "Compatibility cannot be assessed because DB access is failing.",
                "details": (
                    "Fix database reachability first. Current validation is tested against "
                    f"Immich {SUPPORTED_IMMICH_TEST_VERSION}."
                ),
                "testedAgainstImmichVersion": SUPPORTED_IMMICH_TEST_VERSION,
            }

        if database_state is None:
            return {
                "status": DashboardHealthStatus.UNKNOWN.value,
                "summary": "Compatibility is unknown until schema metadata can be read.",
                "details": (
                    "Current validation is tested against Immich "
                    f"{SUPPORTED_IMMICH_TEST_VERSION}. No stronger compatibility claim is made yet."
                ),
                "testedAgainstImmichVersion": SUPPORTED_IMMICH_TEST_VERSION,
            }

        support_status = str(database_state.get("support_status") or "unknown")
        product_version = database_state.get("product_version_current")
        if (
            support_status == DatabaseSchemaSupportStatus.SUPPORTED.value
            and product_version == SUPPORTED_IMMICH_TEST_VERSION
        ):
            return {
                "status": DashboardHealthStatus.OK.value,
                "summary": (
                    f"Detected Immich {product_version}, which matches "
                    "the currently tested validation target."
                ),
                "details": (
                    "This compatibility signal comes from schema detection plus version_history "
                    "metadata, not from a full application-to-database compatibility model."
                ),
                "testedAgainstImmichVersion": SUPPORTED_IMMICH_TEST_VERSION,
            }

        if support_status == DatabaseSchemaSupportStatus.SUPPORTED.value:
            version_label = product_version or "an unknown Immich version"
            return {
                "status": DashboardHealthStatus.WARNING.value,
                "summary": f"Detected {version_label} with a supported schema profile.",
                "details": (
                    "Current validation is tested against Immich "
                    f"{SUPPORTED_IMMICH_TEST_VERSION}. Support beyond "
                    "schema-level detection is not yet modeled."
                ),
                "testedAgainstImmichVersion": SUPPORTED_IMMICH_TEST_VERSION,
            }

        return {
            "status": self._support_status_to_health_status(support_status).value,
            "summary": (
                "Compatibility is limited because the detected schema "
                "profile is not fully supported."
            ),
            "details": (
                f"Detected schema support status: {support_status}. "
                f"Current validation is tested against Immich {SUPPORTED_IMMICH_TEST_VERSION}."
            ),
            "testedAgainstImmichVersion": SUPPORTED_IMMICH_TEST_VERSION,
        }

    def _related_findings(self, settings: AppSettings) -> dict[str, object]:
        if self.catalog_workflow is None:
            return {
                "status": DashboardHealthStatus.UNKNOWN.value,
                "summary": "Consistency linkage is not available in this process.",
                "details": "Open the Consistency page for detailed storage-vs-database findings.",
                "route": "/consistency",
            }

        try:
            job = self.catalog_workflow.get_consistency_job(settings)
        except Exception as exc:
            return {
                "status": DashboardHealthStatus.WARNING.value,
                "summary": "Consistency status could not be loaded for the database overview.",
                "details": str(exc),
                "route": "/consistency",
            }

        result = job.get("result")
        blocked_by = result.get("blockedBy") if isinstance(result, dict) else None
        if isinstance(blocked_by, dict) and blocked_by.get("jobType") == "catalog_inventory_scan":
            return {
                "status": DashboardHealthStatus.WARNING.value,
                "summary": "Consistency findings are waiting for the active storage index scan.",
                "details": str(
                    blocked_by.get("summary") or job.get("summary") or "Waiting for indexing."
                ),
                "route": "/consistency",
            }

        report = result.get("report") if isinstance(result, dict) else None
        if isinstance(report, dict):
            return {
                "status": self._catalog_job_status(job).value,
                "summary": str(job.get("summary") or "Consistency findings are available."),
                "details": (
                    "Open the Consistency page for detailed compare rows "
                    "and repair workflows."
                ),
                "route": "/consistency",
            }

        if isinstance(result, dict) and bool(result.get("requiresScan")):
            return {
                "status": DashboardHealthStatus.WARNING.value,
                "summary": "Consistency findings are waiting for a current storage index.",
                "details": str(
                    job.get("summary")
                    or "A fresh storage scan is required before compare results are current."
                ),
                "route": "/consistency",
            }

        return {
            "status": self._catalog_job_status(job).value,
            "summary": str(
                job.get("summary") or "Consistency findings are available on the Consistency page."
            ),
            "details": "Open the Consistency page for detailed compare rows and repair workflows.",
            "route": "/consistency",
        }

    def _catalog_job_status(self, job: dict[str, object]) -> DashboardHealthStatus:
        state = str(job.get("state") or "pending")
        if state == "completed":
            return DashboardHealthStatus.OK
        if state in {"pending", "running", "partial"}:
            return DashboardHealthStatus.WARNING
        if state == "failed":
            return DashboardHealthStatus.ERROR
        return DashboardHealthStatus.UNKNOWN
