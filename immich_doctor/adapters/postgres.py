from __future__ import annotations

from psycopg import sql

from immich_doctor.core.models import CheckResult, CheckStatus
from immich_doctor.db.connection import (
    can_connect,
    can_execute_query,
    can_reach_tcp,
    can_resolve_host,
    execute_returning_all_composed,
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
    LIST_TABLE_COLUMNS_QUERY,
    LIST_TABLE_FOREIGN_KEYS_QUERY,
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

    def list_columns(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
    ) -> list[dict[str, object]]:
        query = sql.SQL(LIST_TABLE_COLUMNS_QUERY)
        return fetch_all_composed(
            dsn,
            timeout_seconds,
            query,
            (table_schema, table_name),
        )

    def list_foreign_keys(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
    ) -> list[dict[str, object]]:
        query = sql.SQL(LIST_TABLE_FOREIGN_KEYS_QUERY)
        return fetch_all_composed(
            dsn,
            timeout_seconds,
            query,
            (table_schema, table_name),
        )

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
        reference_column: str,
        sample_columns: tuple[str, ...],
        sample_limit: int,
    ) -> dict[str, object]:
        sample_select = [
            sql.SQL("link.{column}").format(column=sql.Identifier(column))
            for column in sample_columns
        ]
        query = sql.SQL(
            """
            WITH missing AS (
                SELECT
                    {sample_select}
                FROM {link_table} AS link
                LEFT JOIN {reference_table} AS ref
                    ON ref.{reference_column} = link.{link_column}
                WHERE ref.{reference_column} IS NULL
            )
            SELECT
                *,
                COUNT(*) OVER() AS broken_reference_count
            FROM missing
            ORDER BY 1 ASC
            LIMIT %s;
            """
        ).format(
            sample_select=sql.SQL(", ").join(sample_select),
            link_table=sql.Identifier(link_schema, link_table),
            reference_table=sql.Identifier(reference_schema, reference_table),
            link_column=sql.Identifier(link_column),
            reference_column=sql.Identifier(reference_column),
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

    def delete_missing_foreign_key_rows(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        link_schema: str,
        link_table: str,
        reference_schema: str,
        reference_table: str,
        link_column: str,
        reference_column: str,
        sample_columns: tuple[str, ...],
        sample_limit: int,
    ) -> dict[str, object]:
        sample_select = [
            sql.SQL("{column}").format(column=sql.Identifier(column))
            for column in sample_columns
        ]
        query = sql.SQL(
            """
            WITH deleted AS (
                DELETE FROM {link_table} AS link
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM {reference_table} AS ref
                    WHERE ref.{reference_column} = link.{link_column}
                )
                RETURNING {sample_select}
            )
            SELECT
                *,
                COUNT(*) OVER() AS broken_reference_count
            FROM deleted
            ORDER BY 1 ASC
            LIMIT %s;
            """
        ).format(
            link_table=sql.Identifier(link_schema, link_table),
            reference_table=sql.Identifier(reference_schema, reference_table),
            link_column=sql.Identifier(link_column),
            reference_column=sql.Identifier(reference_column),
            sample_select=sql.SQL(", ").join(sample_select),
        )

        rows = execute_returning_all_composed(dsn, timeout_seconds, query, (sample_limit,))
        if not rows:
            return {"count": 0, "samples": []}

        count = int(rows[0]["broken_reference_count"])
        samples = [
            {key: value for key, value in row.items() if key != "broken_reference_count"}
            for row in rows
        ]
        return {"count": count, "samples": samples}

    def list_grouped_album_asset_orphans(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        missing_target_table: str,
    ) -> list[dict[str, object]]:
        query = sql.SQL(
            """
            SELECT
                link."albumId" AS "albumId",
                link."assetsId" AS "assetsId",
                COUNT(*) AS row_count
            FROM {album_asset_table} AS link
            LEFT JOIN {target_table} AS target
                ON target.id = link.{target_column}
            WHERE target.id IS NULL
            GROUP BY link."albumId", link."assetsId"
            ORDER BY link."albumId" ASC, link."assetsId" ASC;
            """
        ).format(
            album_asset_table=sql.Identifier("public", "album_asset"),
            target_table=sql.Identifier("public", missing_target_table),
            target_column=sql.Identifier(
                "assetsId" if missing_target_table == "asset" else "albumId"
            ),
        )
        return fetch_all_composed(dsn, timeout_seconds, query)

    def list_asset_files_by_type(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        file_type: str,
    ) -> list[dict[str, object]]:
        query = sql.SQL(
            """
            SELECT
                id,
                "assetId" AS "assetId",
                type,
                path
            FROM {asset_file_table}
            WHERE type = %s
            ORDER BY id ASC;
            """
        ).format(asset_file_table=sql.Identifier("public", "asset_file"))
        return fetch_all_composed(dsn, timeout_seconds, query, (file_type,))

    def delete_album_asset_rows_by_keys(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        album_id: str,
        asset_id: str,
        missing_target_table: str,
    ) -> int:
        target_column = "assetsId" if missing_target_table == "asset" else "albumId"
        query = sql.SQL(
            """
            WITH deleted AS (
                DELETE FROM {album_asset_table} AS link
                WHERE link."albumId" = %s
                AND link."assetsId" = %s
                AND NOT EXISTS (
                    SELECT 1
                    FROM {target_table} AS target
                    WHERE target.id = link.{target_column}
                )
                RETURNING 1
            )
            SELECT COUNT(*) AS deleted_count
            FROM deleted;
            """
        ).format(
            album_asset_table=sql.Identifier("public", "album_asset"),
            target_table=sql.Identifier("public", missing_target_table),
            target_column=sql.Identifier(target_column),
        )
        rows = execute_returning_all_composed(
            dsn,
            timeout_seconds,
            query,
            (album_id, asset_id),
        )
        if not rows:
            return 0
        return int(rows[0]["deleted_count"])
