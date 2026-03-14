from __future__ import annotations

from dataclasses import dataclass, field

from immich_doctor.adapters.postgres import PostgresAdapter
from immich_doctor.core.config import AppSettings
from immich_doctor.core.models import CheckResult, CheckStatus, ValidationReport


@dataclass(slots=True)
class DbHealthCheckService:
    postgres: PostgresAdapter = field(default_factory=PostgresAdapter)

    def run(self, settings: AppSettings) -> ValidationReport:
        host, port = settings.postgres_target()
        dsn = settings.postgres_dsn_value()

        if host is None or port is None:
            return ValidationReport(
                domain="db.health",
                action="check",
                summary="Database health checks failed.",
                checks=[
                    CheckResult(
                        name="postgres_target",
                        status=CheckStatus.FAIL,
                        message="Database host or DSN is not configured.",
                    )
                ],
                metadata={"environment": settings.environment},
            )

        checks = [
            self.postgres.validate_host_resolution(host),
            self.postgres.validate_tcp_connection(
                host=host,
                port=port,
                timeout_seconds=settings.postgres_connect_timeout_seconds,
            ),
        ]

        if dsn is None:
            checks.extend(
                [
                    CheckResult(
                        name="postgres_connection",
                        status=CheckStatus.FAIL,
                        message="Database login credentials are incomplete.",
                    ),
                    CheckResult(
                        name="postgres_round_trip_query",
                        status=CheckStatus.FAIL,
                        message="Database login credentials are incomplete.",
                    ),
                ]
            )
        else:
            checks.append(
                self.postgres.validate_connection(
                    dsn=dsn,
                    timeout_seconds=settings.postgres_connect_timeout_seconds,
                )
            )
            checks.append(
                self.postgres.validate_round_trip_query(
                    dsn=dsn,
                    timeout_seconds=settings.postgres_connect_timeout_seconds,
                )
            )

        return ValidationReport(
            domain="db.health",
            action="check",
            summary="Database health checks completed.",
            checks=checks,
            metadata={"environment": settings.environment},
        )
