from __future__ import annotations

from psycopg import sql

from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.db.connection import (
    can_connect,
    can_execute_query,
    can_reach_tcp,
    can_resolve_host,
    fetch_all,
    fetch_all_composed,
)
from immich_doctor.db.queries import (
    LIST_ALL_INDEXES_QUERY,
    LIST_BASE_TABLES_QUERY,
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

    def list_tables(self, dsn: str, timeout_seconds: int) -> list[dict[str, object]]:
        return fetch_all(dsn, timeout_seconds, LIST_BASE_TABLES_QUERY)

    def find_missing_foreign_key_rows(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        link_schema: str,
        link_table: str,
        reference_schema: str,
        reference_table: str,
        link_column: str,
        sample_limit: int,
    ) -> dict[str, object]:
        query = sql.SQL(
            """
            WITH missing AS (
                SELECT
                    link.asset_id,
                    link.album_id
                FROM {link_table} AS link
                LEFT JOIN {reference_table} AS ref
                    ON ref.id = link.{link_column}
                WHERE ref.id IS NULL
            )
            SELECT
                asset_id,
                album_id,
                COUNT(*) OVER() AS broken_reference_count
            FROM missing
            ORDER BY album_id ASC, asset_id ASC
            LIMIT %s;
            """
        ).format(
            link_table=sql.Identifier(link_schema, link_table),
            reference_table=sql.Identifier(reference_schema, reference_table),
            link_column=sql.Identifier(link_column),
        )

        rows = fetch_all_composed(dsn, timeout_seconds, query, (sample_limit,))
        if not rows:
            return {"count": 0, "samples": []}

        count = int(rows[0]["broken_reference_count"])
        samples = [
            {key: value for key, value in row.items() if key != "broken_reference_count"}
            for row in rows
        ]
        return {"count": count, "samples": samples}
