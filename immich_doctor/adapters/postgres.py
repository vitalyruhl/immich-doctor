from __future__ import annotations

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

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

    def fetch_database_size_bytes(self, dsn: str, timeout_seconds: int) -> int:
        rows = fetch_all(
            dsn,
            timeout_seconds,
            "SELECT pg_database_size(current_database()) AS size_bytes;",
        )
        if not rows:
            raise ValueError("Database size query returned no rows.")
        return int(rows[0]["size_bytes"])

    def fetch_server_version(self, dsn: str, timeout_seconds: int) -> dict[str, str]:
        rows = fetch_all(
            dsn,
            timeout_seconds,
            (
                "SELECT "
                "current_setting('server_version') AS server_version, "
                "current_setting('server_version_num') AS server_version_num, "
                "version() AS full_version;"
            ),
        )
        if not rows:
            raise ValueError("Server version query returned no rows.")
        row = rows[0]
        return {
            "server_version": str(row["server_version"]),
            "server_version_num": str(row["server_version_num"]),
            "full_version": str(row["full_version"]),
        }

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

    def list_version_history_entries(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
        version_column: str,
        created_at_column: str | None = None,
        entry_id_column: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        selected_columns: list[sql.Composable] = []
        if entry_id_column is None:
            selected_columns.append(sql.SQL("NULL::text AS entry_id"))
        else:
            selected_columns.append(
                sql.SQL("{column}::text AS entry_id").format(column=sql.Identifier(entry_id_column))
            )
        if created_at_column is None:
            selected_columns.append(sql.SQL("NULL::text AS created_at"))
            order_clause = sql.SQL("")
        else:
            selected_columns.append(
                sql.SQL("{column}::text AS created_at").format(
                    column=sql.Identifier(created_at_column)
                )
            )
            order_clause = sql.SQL(" ORDER BY {column} DESC").format(
                column=sql.Identifier(created_at_column)
            )
        selected_columns.append(
            sql.SQL("{column}::text AS version").format(column=sql.Identifier(version_column))
        )
        query = sql.SQL(
            """
            SELECT
                {selected_columns}
            FROM {table_name}{order_clause}
            LIMIT %s;
            """
        ).format(
            selected_columns=sql.SQL(", ").join(selected_columns),
            table_name=sql.Identifier(table_schema, table_name),
            order_clause=order_clause,
        )
        return fetch_all_composed(dsn, timeout_seconds, query, (limit,))

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
            sql.SQL("{column}").format(column=sql.Identifier(column)) for column in sample_columns
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
        asset_reference_column: str,
    ) -> list[dict[str, object]]:
        query = sql.SQL(
            """
            SELECT
                link."albumId" AS "albumId",
                link.{asset_reference_column} AS "assetId",
                COUNT(*) AS row_count
            FROM {album_asset_table} AS link
            LEFT JOIN {target_table} AS target
                ON target.id = link.{target_column}
            WHERE link.{target_column} IS NOT NULL
            AND target.id IS NULL
            GROUP BY link."albumId", link.{asset_reference_column}
            ORDER BY link."albumId" ASC, link.{asset_reference_column} ASC;
            """
        ).format(
            album_asset_table=sql.Identifier("public", "album_asset"),
            target_table=sql.Identifier("public", missing_target_table),
            target_column=sql.Identifier(
                asset_reference_column if missing_target_table == "asset" else "albumId"
            ),
            asset_reference_column=sql.Identifier(asset_reference_column),
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

    def list_all_assets_for_catalog_consistency(
        self,
        dsn: str,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        asset_columns = {
            str(row["column_name"])
            for row in self.list_columns(
                dsn,
                timeout_seconds,
                table_schema="public",
                table_name="asset",
            )
        }
        optional_columns = [
            column
            for column in (
                "checksum",
                "originalChecksum",
                "checksumAlgorithm",
                "livePhotoVideoId",
            )
            if column in asset_columns
        ]
        select_columns: list[sql.Composable] = [
            sql.SQL("id"),
            sql.SQL("type"),
            sql.SQL('"ownerId" AS "ownerId"'),
            sql.SQL('"createdAt" AS "createdAt"'),
            sql.SQL('"updatedAt" AS "updatedAt"'),
            sql.SQL('"originalFileName" AS "originalFileName"'),
            sql.SQL('"originalPath" AS "originalPath"'),
            sql.SQL('"encodedVideoPath" AS "encodedVideoPath"'),
        ]
        for column in optional_columns:
            select_columns.append(
                sql.SQL("{column} AS {alias}").format(
                    column=sql.Identifier(column),
                    alias=sql.Identifier(column),
                )
            )
        query = sql.SQL(
            """
            SELECT
                {select_columns}
            FROM {asset_table}
            ORDER BY id ASC;
            """
        ).format(
            select_columns=sql.SQL(", ").join(select_columns),
            asset_table=sql.Identifier("public", "asset"),
        )
        return fetch_all_composed(dsn, timeout_seconds, query)

    def list_all_asset_files_for_catalog_consistency(
        self,
        dsn: str,
        timeout_seconds: int,
    ) -> list[dict[str, object]]:
        query = sql.SQL(
            """
            SELECT
                id,
                "assetId" AS "assetId",
                type,
                path
            FROM {asset_file_table}
            ORDER BY "assetId" ASC, type ASC, id ASC;
            """
        ).format(asset_file_table=sql.Identifier("public", "asset_file"))
        return fetch_all_composed(dsn, timeout_seconds, query)

    def list_assets_for_runtime_integrity(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, object]]:
        query = sql.SQL(
            """
            SELECT
                id,
                type,
                "originalPath" AS "originalPath"
            FROM {asset_table}
            ORDER BY id ASC
            LIMIT %s OFFSET %s;
            """
        ).format(asset_table=sql.Identifier("public", "asset"))
        return fetch_all_composed(dsn, timeout_seconds, query, (limit, offset))

    def list_assets_for_missing_references(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        limit: int,
        offset: int,
        optional_columns: tuple[str, ...] = (),
    ) -> list[dict[str, object]]:
        select_columns: list[sql.Composable] = [
            sql.SQL("id"),
            sql.SQL("type"),
            sql.SQL('"originalPath" AS "originalPath"'),
        ]
        for column in optional_columns:
            select_columns.append(
                sql.SQL("{column} AS {alias}").format(
                    column=sql.Identifier(column),
                    alias=sql.Identifier(column),
                )
            )

        query = sql.SQL(
            """
            SELECT
                {select_columns}
            FROM {asset_table}
            ORDER BY id ASC
            LIMIT %s OFFSET %s;
            """
        ).format(
            select_columns=sql.SQL(", ").join(select_columns),
            asset_table=sql.Identifier("public", "asset"),
        )
        return fetch_all_composed(dsn, timeout_seconds, query, (limit, offset))

    def list_asset_files_for_assets(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        asset_ids: tuple[str, ...],
    ) -> list[dict[str, object]]:
        if not asset_ids:
            return []

        query = sql.SQL(
            """
            SELECT
                id,
                "assetId" AS "assetId",
                type,
                path
            FROM {asset_file_table}
            WHERE "assetId" = ANY(%s)
            ORDER BY "assetId" ASC, id ASC;
            """
        ).format(asset_file_table=sql.Identifier("public", "asset_file"))
        return fetch_all_composed(dsn, timeout_seconds, query, (list(asset_ids),))

    def list_rows_by_column_values(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
        column_name: str,
        values: tuple[str, ...],
        order_columns: tuple[str, ...] = (),
    ) -> list[dict[str, object]]:
        if not values:
            return []

        order_clause = (
            sql.SQL(" ORDER BY {columns}").format(
                columns=sql.SQL(", ").join(sql.Identifier(column) for column in order_columns)
            )
            if order_columns
            else sql.SQL("")
        )
        query = sql.SQL(
            """
            SELECT *
            FROM {table_name}
            WHERE {column_name} = ANY(%s){order_clause};
            """
        ).format(
            table_name=sql.Identifier(table_schema, table_name),
            column_name=sql.Identifier(column_name),
            order_clause=order_clause,
        )
        return fetch_all_composed(dsn, timeout_seconds, query, (list(values),))

    def delete_rows_by_column_values_returning_all(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
        column_name: str,
        values: tuple[str, ...],
    ) -> list[dict[str, object]]:
        if not values:
            return []

        query = sql.SQL(
            """
            DELETE FROM {table_name}
            WHERE {column_name} = ANY(%s)
            RETURNING *;
            """
        ).format(
            table_name=sql.Identifier(table_schema, table_name),
            column_name=sql.Identifier(column_name),
        )
        return execute_returning_all_composed(dsn, timeout_seconds, query, (list(values),))

    def insert_rows(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        table_schema: str,
        table_name: str,
        rows: list[dict[str, object]],
    ) -> int:
        if not rows:
            return 0

        columns = tuple(rows[0].keys())
        values_sql = []
        params: list[object] = []
        for row in rows:
            values_sql.append(
                sql.SQL("({placeholders})").format(
                    placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in columns)
                )
            )
            params.extend(row[column] for column in columns)

        query = sql.SQL(
            """
            INSERT INTO {table_name} ({columns})
            VALUES {values};
            """
        ).format(
            table_name=sql.Identifier(table_schema, table_name),
            columns=sql.SQL(", ").join(sql.Identifier(column) for column in columns),
            values=sql.SQL(", ").join(values_sql),
        )
        execute_returning_all_composed(dsn, timeout_seconds, query, tuple(params))
        return len(rows)

    def delete_asset_reference_records(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        asset_id: str,
        relations: tuple[dict[str, str], ...],
    ) -> list[dict[str, object]]:
        deleted_records: list[dict[str, object]] = []
        with psycopg.connect(
            dsn,
            connect_timeout=timeout_seconds,
            row_factory=dict_row,
        ) as connection:
            try:
                with connection.cursor() as cursor:
                    for relation in relations:
                        query = sql.SQL(
                            """
                            DELETE FROM {table_name}
                            WHERE {column_name} = %s
                            RETURNING *;
                            """
                        ).format(
                            table_name=sql.Identifier(
                                relation["table_schema"],
                                relation["table_name"],
                            ),
                            column_name=sql.Identifier(relation["column_name"]),
                        )
                        cursor.execute(query, (asset_id,))
                        rows = [dict(row) for row in cursor.fetchall()]
                        if rows:
                            deleted_records.append(
                                {
                                    "table": (
                                        f"{relation['table_schema']}.{relation['table_name']}"
                                    ),
                                    "rows": rows,
                                }
                            )

                    asset_query = sql.SQL(
                        """
                        DELETE FROM {asset_table}
                        WHERE id = %s
                        RETURNING *;
                        """
                    ).format(asset_table=sql.Identifier("public", "asset"))
                    cursor.execute(asset_query, (asset_id,))
                    asset_rows = [dict(row) for row in cursor.fetchall()]
                    if not asset_rows:
                        raise ValueError("Asset row was not deleted because it no longer exists.")
                    deleted_records.insert(0, {"table": "public.asset", "rows": asset_rows})
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return deleted_records

    def restore_asset_reference_records(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        records: list[dict[str, object]],
    ) -> int:
        inserted_total = 0
        ordered_records = sorted(
            records,
            key=lambda item: (0 if item["table"] == "public.asset" else 1, str(item["table"])),
        )
        with psycopg.connect(
            dsn,
            connect_timeout=timeout_seconds,
            row_factory=dict_row,
        ) as connection:
            try:
                with connection.cursor() as cursor:
                    for record in ordered_records:
                        table_schema, table_name = str(record["table"]).split(".", maxsplit=1)
                        rows = list(record.get("rows", []))
                        if not rows:
                            continue
                        columns = tuple(rows[0].keys())
                        values_sql = []
                        params: list[object] = []
                        for row in rows:
                            values_sql.append(
                                sql.SQL("({placeholders})").format(
                                    placeholders=sql.SQL(", ").join(
                                        sql.Placeholder() for _ in columns
                                    )
                                )
                            )
                            params.extend(row[column] for column in columns)
                        query = sql.SQL(
                            """
                            INSERT INTO {table_name} ({columns})
                            VALUES {values};
                            """
                        ).format(
                            table_name=sql.Identifier(table_schema, table_name),
                            columns=sql.SQL(", ").join(
                                sql.Identifier(column) for column in columns
                            ),
                            values=sql.SQL(", ").join(values_sql),
                        )
                        cursor.execute(query, tuple(params))
                        inserted_total += len(rows)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return inserted_total

    def list_metadata_failure_candidates(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, object]]:
        query = sql.SQL(
            """
            SELECT
                asset.id,
                asset.type,
                asset."originalPath" AS "originalPath",
                status."metadataExtractedAt" AS "metadataExtractedAt"
            FROM {asset_job_status_table} AS status
            JOIN {asset_table} AS asset
                ON asset.id = status."assetId"
            WHERE status."metadataExtractedAt" IS NULL
            ORDER BY asset.id ASC
            LIMIT %s OFFSET %s;
            """
        ).format(
            asset_job_status_table=sql.Identifier("public", "asset_job_status"),
            asset_table=sql.Identifier("public", "asset"),
        )
        return fetch_all_composed(dsn, timeout_seconds, query, (limit, offset))

    def delete_album_asset_rows_by_keys(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        album_id: str,
        asset_id: str,
        missing_target_table: str,
        asset_reference_column: str,
    ) -> int:
        target_column = asset_reference_column if missing_target_table == "asset" else "albumId"
        query = sql.SQL(
            """
            WITH deleted AS (
                DELETE FROM {album_asset_table} AS link
                WHERE link."albumId" = %s
                AND link.{asset_reference_column} = %s
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
            asset_reference_column=sql.Identifier(asset_reference_column),
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

    def update_asset_original_path(
        self,
        dsn: str,
        timeout_seconds: int,
        *,
        asset_id: str,
        new_original_path: str,
    ) -> dict[str, object]:
        query = sql.SQL(
            """
            WITH previous AS (
                SELECT id, "originalPath" AS "oldOriginalPath"
                FROM {asset_table}
                WHERE id = %s
            ),
            updated AS (
                UPDATE {asset_table}
                SET "originalPath" = %s
                WHERE id = %s
                RETURNING id, "originalPath" AS "newOriginalPath"
            )
            SELECT
                updated.id,
                previous."oldOriginalPath",
                updated."newOriginalPath"
            FROM updated
            JOIN previous
              ON previous.id = updated.id;
            """
        ).format(asset_table=sql.Identifier("public", "asset"))
        rows = execute_returning_all_composed(
            dsn,
            timeout_seconds,
            query,
            (asset_id, new_original_path, asset_id),
        )
        if not rows:
            raise ValueError("Asset originalPath update returned no rows.")
        return dict(rows[0])
