from __future__ import annotations

from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.db.connection import can_connect, can_reach_tcp, can_resolve_host


class PostgresAdapter:
    def validate_connection(self, dsn: str, timeout_seconds: int) -> CheckResult:
        connected, message = can_connect(dsn, timeout_seconds)
        return CheckResult(
            name="postgres_connection",
            status=CheckStatus.PASS if connected else CheckStatus.FAIL,
            message=message,
        )

    def validate_host_resolution(self, host: str) -> CheckResult:
        resolved, message = can_resolve_host(host)
        return CheckResult(
            name="postgres_host_resolution",
            status=CheckStatus.PASS if resolved else CheckStatus.FAIL,
            message=message,
            details={"host": host},
        )

    def validate_tcp_connection(self, host: str, port: int, timeout_seconds: int) -> CheckResult:
        reachable, message = can_reach_tcp(host, port, timeout_seconds)
        return CheckResult(
            name="postgres_tcp_connection",
            status=CheckStatus.PASS if reachable else CheckStatus.FAIL,
            message=message,
            details={"host": host, "port": port},
        )
