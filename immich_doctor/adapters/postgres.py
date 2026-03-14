from __future__ import annotations

from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.db.connection import (
    can_connect,
    can_execute_query,
    can_reach_tcp,
    can_resolve_host,
    fetch_all,
)
from immich_doctor.db.queries import (
    LIST_ALL_INDEXES_QUERY,
    LIST_INDEX_SIZES_QUERY,
    LIST_INDEX_USAGE_STATS_QUERY,
    LIST_INVALID_INDEXES_QUERY,
    LIST_MISSING_FK_INDEXES_QUERY,
)


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

    def validate_round_trip_query(self, dsn: str, timeout_seconds: int) -> CheckResult:
        executed, message = can_execute_query(dsn, timeout_seconds)
        return CheckResult(
            name="postgres_round_trip_query",
            status=CheckStatus.PASS if executed else CheckStatus.FAIL,
            message=message,
        )

    def list_indexes(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return fetch_all(dsn, timeout_seconds, LIST_ALL_INDEXES_QUERY)

    def list_invalid_indexes(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return fetch_all(dsn, timeout_seconds, LIST_INVALID_INDEXES_QUERY)

    def list_index_usage_stats(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return fetch_all(dsn, timeout_seconds, LIST_INDEX_USAGE_STATS_QUERY)

    def list_index_sizes(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return fetch_all(dsn, timeout_seconds, LIST_INDEX_SIZES_QUERY)

    def list_missing_fk_indexes(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return fetch_all(dsn, timeout_seconds, LIST_MISSING_FK_INDEXES_QUERY)
