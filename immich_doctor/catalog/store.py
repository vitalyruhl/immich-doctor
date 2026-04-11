from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from immich_doctor.catalog.models import CatalogFileObservation, CatalogRootSpec
from immich_doctor.catalog.paths import catalog_database_path, catalog_root
from immich_doctor.core.config import AppSettings


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class CatalogStore:
    def initialize(self, settings: AppSettings) -> None:
        catalog_root(settings).mkdir(parents=True, exist_ok=True)
        with self.connect(settings) as connection:
            connection.executescript(_SCHEMA_SQL)
            self._ensure_schema_columns(connection)
            connection.commit()

    @contextmanager
    def connect(self, settings: AppSettings) -> Iterator[sqlite3.Connection]:
        database_path = catalog_database_path(settings)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA synchronous=FULL;")
        connection.execute("PRAGMA foreign_keys=ON;")
        connection.execute("PRAGMA busy_timeout=5000;")
        try:
            yield connection
        finally:
            connection.close()

    def upsert_storage_root(self, settings: AppSettings, root: CatalogRootSpec) -> int:
        self.initialize(settings)
        now = _utcnow()
        with self.connect(settings) as connection:
            connection.execute(
                """
                INSERT INTO storage_root (
                    slug,
                    setting_name,
                    root_type,
                    absolute_path,
                    path_case_sensitive,
                    enabled,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    setting_name = excluded.setting_name,
                    root_type = excluded.root_type,
                    absolute_path = excluded.absolute_path,
                    updated_at = CASE
                        WHEN storage_root.setting_name != excluded.setting_name
                          OR storage_root.root_type != excluded.root_type
                          OR storage_root.absolute_path != excluded.absolute_path
                          OR storage_root.enabled != 1
                        THEN excluded.updated_at
                        ELSE storage_root.updated_at
                    END,
                    enabled = 1;
                """,
                (
                    root.slug,
                    root.setting_name,
                    root.root_type,
                    str(root.path),
                    1,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT id FROM storage_root WHERE slug = ?;",
                (root.slug,),
            ).fetchone()
            connection.commit()
        if row is None:
            raise ValueError(f"Catalog root `{root.slug}` could not be persisted.")
        return int(row["id"])

    def list_storage_roots(self, settings: AppSettings) -> list[dict[str, object]]:
        self.initialize(settings)
        with self.connect(settings) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    slug,
                    setting_name,
                    root_type,
                    absolute_path,
                    enabled,
                    created_at,
                    updated_at
                FROM storage_root
                WHERE enabled = 1
                ORDER BY slug ASC;
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_storage_root_by_slug(
        self,
        settings: AppSettings,
        slug: str,
    ) -> dict[str, object] | None:
        self.initialize(settings)
        with self.connect(settings) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    slug,
                    setting_name,
                    root_type,
                    absolute_path,
                    enabled,
                    created_at,
                    updated_at
                FROM storage_root
                WHERE slug = ? AND enabled = 1;
                """,
                (slug,),
            ).fetchone()
        return dict(row) if row is not None else None

    def create_scan_session(
        self,
        settings: AppSettings,
        *,
        storage_root_id: int,
        max_files: int | None,
    ) -> dict[str, object]:
        self.initialize(settings)
        session_id = uuid4().hex
        started_at = _utcnow()
        generation = self._next_generation(settings, storage_root_id=storage_root_id)
        with self.connect(settings) as connection:
            cursor = connection.execute(
                """
                INSERT INTO scan_snapshot (
                    storage_root_id,
                    source_scan_session_id,
                    snapshot_kind,
                    generation,
                    status,
                    started_at
                )
                VALUES (?, ?, 'inventory', ?, 'running', ?);
                """,
                (storage_root_id, session_id, generation, started_at),
            )
            snapshot_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO scan_session (
                    id,
                    storage_root_id,
                    snapshot_id,
                    status,
                    started_at,
                    heartbeat_at,
                    max_files
                )
                VALUES (?, ?, ?, 'running', ?, ?, ?);
                """,
                (session_id, storage_root_id, snapshot_id, started_at, started_at, max_files),
            )
            connection.execute(
                """
                INSERT INTO scan_collect_queue (
                    scan_session_id,
                    relative_path,
                    status,
                    discovered_at
                )
                VALUES (?, '', 'pending', ?);
                """,
                (session_id, started_at),
            )
            connection.commit()
        session = self.get_scan_session(settings, session_id)
        if session is None:
            raise ValueError(f"Scan session `{session_id}` could not be created.")
        return session

    def get_scan_session(self, settings: AppSettings, session_id: str) -> dict[str, object] | None:
        self.initialize(settings)
        with self.connect(settings) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    storage_root_id,
                    snapshot_id,
                    status,
                    started_at,
                    heartbeat_at,
                    completed_at,
                    max_files,
                    files_seen,
                    bytes_seen,
                    directories_completed,
                    error_count,
                    last_relative_path
                FROM scan_session
                WHERE id = ?;
                """,
                (session_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def reopen_scan_session(
        self,
        settings: AppSettings,
        session_id: str,
    ) -> dict[str, object] | None:
        self.initialize(settings)
        now = _utcnow()
        with self.connect(settings) as connection:
            connection.execute(
                """
                UPDATE scan_directory_queue
                SET status = 'pending'
                    , worker_id = NULL
                WHERE scan_session_id = ? AND status = 'processing';
                """,
                (session_id,),
            )
            connection.execute(
                """
                UPDATE scan_collect_queue
                SET status = 'pending'
                WHERE scan_session_id = ? AND status = 'processing';
                """,
                (session_id,),
            )
            connection.execute(
                """
                UPDATE scan_session
                SET status = 'running',
                    heartbeat_at = ?
                WHERE id = ? AND status IN ('paused', 'stopped', 'failed', 'running');
                """,
                (now, session_id),
            )
            connection.commit()
        return self.get_scan_session(settings, session_id)

    def find_latest_incomplete_scan_session(
        self,
        settings: AppSettings,
    ) -> dict[str, object] | None:
        self.initialize(settings)
        with self.connect(settings) as connection:
            row = connection.execute(
                """
                SELECT
                    session.id,
                    session.status,
                    session.started_at,
                    session.heartbeat_at,
                    session.completed_at,
                    session.max_files,
                    session.files_seen,
                    session.bytes_seen,
                    session.directories_completed,
                    session.error_count,
                    session.last_relative_path,
                    session.snapshot_id,
                    root.slug AS root_slug,
                    root.root_type AS root_type,
                    root.absolute_path AS root_path
                FROM scan_session AS session
                JOIN storage_root AS root
                  ON root.id = session.storage_root_id
                                WHERE session.status IN ('running', 'paused', 'stopped')
                ORDER BY session.started_at DESC
                LIMIT 1;
                """
            ).fetchone()
        return dict(row) if row is not None else None

    def claim_next_directory(
        self,
        settings: AppSettings,
        session_id: str,
        *,
        worker_id: str,
    ) -> dict[str, object] | None:
        self.initialize(settings)
        with self.connect(settings) as connection:
            connection.execute("BEGIN IMMEDIATE;")
            row = connection.execute(
                """
                SELECT
                    id,
                    relative_path,
                    payload_json,
                    payload_file_count,
                    payload_error_count,
                    payload_bytes_delta,
                    payload_last_relative_path
                FROM scan_directory_queue
                WHERE scan_session_id = ? AND status = 'pending'
                ORDER BY relative_path ASC
                LIMIT 1;
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                return None
            relative_path = str(row["relative_path"])
            connection.execute(
                """
                UPDATE scan_directory_queue
                SET status = 'processing',
                    worker_id = ?
                WHERE scan_session_id = ? AND relative_path = ?;
                """,
                (worker_id, session_id, relative_path),
            )
            connection.commit()
        return dict(row)

    def claim_next_collect_directories(
        self,
        settings: AppSettings,
        session_id: str,
        *,
        limit: int,
    ) -> list[str]:
        self.initialize(settings)
        with self.connect(settings) as connection:
            connection.execute("BEGIN IMMEDIATE;")
            rows = connection.execute(
                """
                SELECT relative_path
                FROM scan_collect_queue
                WHERE scan_session_id = ? AND status = 'pending'
                ORDER BY relative_path ASC
                LIMIT ?;
                """,
                (session_id, limit),
            ).fetchall()
            if not rows:
                connection.rollback()
                return []
            relative_paths = [str(row["relative_path"]) for row in rows]
            connection.executemany(
                """
                UPDATE scan_collect_queue
                SET status = 'processing'
                WHERE scan_session_id = ? AND relative_path = ?;
                """,
                [(session_id, relative_path) for relative_path in relative_paths],
            )
            connection.commit()
        return relative_paths

    def seed_directory_queue(
        self,
        settings: AppSettings,
        *,
        session_id: str,
        relative_paths: list[str],
    ) -> None:
        self.initialize(settings)
        if not relative_paths:
            return

        now = _utcnow()
        unique_paths = sorted(set(relative_paths))
        with self.connect(settings) as connection:
            connection.execute("BEGIN IMMEDIATE;")
            connection.executemany(
                """
                INSERT INTO scan_directory_queue (
                    scan_session_id,
                    relative_path,
                    status,
                    worker_id,
                    discovered_at
                )
                VALUES (?, ?, 'pending', NULL, ?)
                ON CONFLICT(scan_session_id, relative_path) DO NOTHING;
                """,
                [(session_id, relative_path, now) for relative_path in unique_paths],
            )
            connection.commit()

    def seed_collect_queue(
        self,
        settings: AppSettings,
        *,
        session_id: str,
        relative_paths: list[str],
    ) -> None:
        self.initialize(settings)
        if not relative_paths:
            return

        now = _utcnow()
        unique_paths = sorted(set(relative_paths))
        with self.connect(settings) as connection:
            connection.execute("BEGIN IMMEDIATE;")
            connection.executemany(
                """
                INSERT INTO scan_collect_queue (
                    scan_session_id,
                    relative_path,
                    status,
                    discovered_at
                )
                VALUES (?, ?, 'pending', ?)
                ON CONFLICT(scan_session_id, relative_path) DO NOTHING;
                """,
                [(session_id, relative_path, now) for relative_path in unique_paths],
            )
            connection.commit()

    def apply_directory_files(
        self,
        settings: AppSettings,
        *,
        session_id: str,
        storage_root_id: int,
        snapshot_id: int,
        relative_path: str,
        file_observations: list[CatalogFileObservation],
        error_count: int,
        bytes_delta: int,
        last_relative_path: str | None,
    ) -> None:
        self.initialize(settings)
        now = _utcnow()
        with self.connect(settings) as connection:
            connection.execute("BEGIN IMMEDIATE;")
            for observation in file_observations:
                connection.execute(
                    """
                    INSERT INTO file_record (
                        storage_root_id,
                        relative_path,
                        parent_relative_path,
                        file_name,
                        extension,
                        size_bytes,
                        created_at_fs,
                        modified_at_fs,
                        first_seen_at,
                        last_seen_at,
                        first_seen_snapshot_id,
                        last_seen_snapshot_id,
                        last_scan_session_id,
                        file_type_guess,
                        media_class_guess,
                        zero_byte_flag,
                        stat_device,
                        stat_inode,
                        hash_status,
                        presence_status
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?,
                        'not_requested', 'present'
                    )
                    ON CONFLICT(storage_root_id, relative_path) DO UPDATE SET
                        parent_relative_path = excluded.parent_relative_path,
                        file_name = excluded.file_name,
                        extension = excluded.extension,
                        size_bytes = excluded.size_bytes,
                        created_at_fs = COALESCE(file_record.created_at_fs, excluded.created_at_fs),
                        modified_at_fs = excluded.modified_at_fs,
                        last_seen_at = excluded.last_seen_at,
                        last_seen_snapshot_id = excluded.last_seen_snapshot_id,
                        last_scan_session_id = excluded.last_scan_session_id,
                        file_type_guess = excluded.file_type_guess,
                        media_class_guess = excluded.media_class_guess,
                        zero_byte_flag = excluded.zero_byte_flag,
                        stat_device = excluded.stat_device,
                        stat_inode = excluded.stat_inode,
                        presence_status = 'present';
                    """,
                    (
                        storage_root_id,
                        observation.relative_path,
                        observation.parent_relative_path,
                        observation.file_name,
                        observation.extension,
                        observation.size_bytes,
                        observation.created_at_fs,
                        observation.modified_at_fs,
                        now,
                        now,
                        snapshot_id,
                        snapshot_id,
                        session_id,
                        observation.file_type_guess,
                        observation.media_class_guess,
                        1 if observation.zero_byte_flag else 0,
                        observation.stat_device,
                        observation.stat_inode,
                    ),
                )
            connection.execute(
                """
                UPDATE scan_directory_queue
                SET status = 'done',
                    worker_id = NULL,
                    payload_json = NULL,
                    completed_at = ?
                WHERE scan_session_id = ? AND relative_path = ?;
                """,
                (now, session_id, relative_path),
            )
            connection.execute(
                """
                UPDATE scan_session
                SET heartbeat_at = ?,
                    files_seen = files_seen + ?,
                    bytes_seen = bytes_seen + ?,
                    directories_completed = directories_completed + 1,
                    error_count = error_count + ?,
                    last_relative_path = COALESCE(?, last_relative_path)
                WHERE id = ?;
                """,
                (
                    now,
                    len(file_observations),
                    bytes_delta,
                    error_count,
                    last_relative_path,
                    session_id,
                ),
            )
            connection.commit()

    def complete_collected_directories(
        self,
        settings: AppSettings,
        *,
        session_id: str,
        collected_rows: list[dict[str, object]],
    ) -> None:
        self.initialize(settings)
        now = _utcnow()
        with self.connect(settings) as connection:
            connection.execute("BEGIN IMMEDIATE;")
            for row in collected_rows:
                relative_path = str(row["relative_path"])
                child_relative_paths = sorted(set(row.get("child_relative_paths") or []))
                file_observations = [
                    item.to_dict() for item in row.get("file_observations", [])
                ]
                payload_json = json.dumps(file_observations, separators=(",", ":"))
                payload_file_count = len(file_observations)
                payload_error_count = int(row.get("error_count") or 0)
                payload_bytes_delta = int(row.get("bytes_delta") or 0)
                payload_last_relative_path = row.get("last_relative_path")
                connection.execute(
                    """
                    UPDATE scan_collect_queue
                    SET status = 'done',
                        completed_at = ?
                    WHERE scan_session_id = ? AND relative_path = ?;
                    """,
                    (now, session_id, relative_path),
                )
                connection.execute(
                    """
                    INSERT INTO scan_directory_queue (
                        scan_session_id,
                        relative_path,
                        status,
                        worker_id,
                        discovered_at,
                        payload_json,
                        payload_file_count,
                        payload_error_count,
                        payload_bytes_delta,
                        payload_last_relative_path
                    )
                    VALUES (?, ?, 'pending', NULL, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(scan_session_id, relative_path) DO UPDATE SET
                        status = 'pending',
                        worker_id = NULL,
                        payload_json = excluded.payload_json,
                        payload_file_count = excluded.payload_file_count,
                        payload_error_count = excluded.payload_error_count,
                        payload_bytes_delta = excluded.payload_bytes_delta,
                        payload_last_relative_path = excluded.payload_last_relative_path;
                    """,
                    (
                        session_id,
                        relative_path,
                        now,
                        payload_json,
                        payload_file_count,
                        payload_error_count,
                        payload_bytes_delta,
                        payload_last_relative_path,
                    ),
                )
                if child_relative_paths:
                    connection.executemany(
                        """
                        INSERT INTO scan_collect_queue (
                            scan_session_id,
                            relative_path,
                            status,
                            discovered_at
                        )
                        VALUES (?, ?, 'pending', ?)
                        ON CONFLICT(scan_session_id, relative_path) DO NOTHING;
                        """,
                        [(session_id, child_path, now) for child_path in child_relative_paths],
                    )
            connection.commit()

    def mark_session_paused(
        self,
        settings: AppSettings,
        session_id: str,
    ) -> dict[str, object] | None:
        self.initialize(settings)
        now = _utcnow()
        with self.connect(settings) as connection:
            connection.execute(
                """
                UPDATE scan_session
                SET status = 'paused',
                    heartbeat_at = ?
                WHERE id = ?;
                """,
                (now, session_id),
            )
            connection.commit()
        return self.get_scan_session(settings, session_id)

    def mark_session_stopped(
        self,
        settings: AppSettings,
        session_id: str,
    ) -> dict[str, object] | None:
        self.initialize(settings)
        now = _utcnow()
        with self.connect(settings) as connection:
            connection.execute(
                """
                UPDATE scan_session
                SET status = 'stopped',
                    heartbeat_at = ?,
                    completed_at = ?
                WHERE id = ?;
                """,
                (now, now, session_id),
            )
            connection.commit()
        return self.get_scan_session(settings, session_id)

    def requeue_processing_directories(self, settings: AppSettings, session_id: str) -> None:
        self.initialize(settings)
        with self.connect(settings) as connection:
            connection.execute(
                """
                UPDATE scan_directory_queue
                SET status = 'pending'
                    , worker_id = NULL
                WHERE scan_session_id = ?
                  AND status = 'processing';
                """,
                (session_id,),
            )
            connection.commit()

    def requeue_processing_directories_for_worker(
        self,
        settings: AppSettings,
        session_id: str,
        *,
        worker_id: str,
    ) -> None:
        self.initialize(settings)
        with self.connect(settings) as connection:
            connection.execute(
                """
                UPDATE scan_directory_queue
                SET status = 'pending',
                    worker_id = NULL
                WHERE scan_session_id = ?
                  AND status = 'processing'
                  AND worker_id = ?;
                """,
                (session_id, worker_id),
            )
            connection.commit()

    def requeue_collecting_directories(self, settings: AppSettings, session_id: str) -> None:
        self.initialize(settings)
        with self.connect(settings) as connection:
            connection.execute(
                """
                UPDATE scan_collect_queue
                SET status = 'pending'
                WHERE scan_session_id = ?
                  AND status = 'processing';
                """,
                (session_id,),
            )
            connection.commit()

    def mark_session_failed(
        self,
        settings: AppSettings,
        session_id: str,
    ) -> dict[str, object] | None:
        self.initialize(settings)
        now = _utcnow()
        with self.connect(settings) as connection:
            connection.execute(
                """
                UPDATE scan_session
                SET status = 'failed',
                    heartbeat_at = ?,
                    completed_at = ?
                WHERE id = ?;
                """,
                (now, now, session_id),
            )
            snapshot_id_row = connection.execute(
                "SELECT snapshot_id FROM scan_session WHERE id = ?;",
                (session_id,),
            ).fetchone()
            if snapshot_id_row is not None:
                connection.execute(
                    """
                    UPDATE scan_snapshot
                    SET status = 'failed'
                    WHERE id = ?;
                    """,
                    (int(snapshot_id_row["snapshot_id"]),),
                )
            connection.commit()
        return self.get_scan_session(settings, session_id)

    def commit_scan_session(
        self,
        settings: AppSettings,
        session_id: str,
    ) -> dict[str, object] | None:
        self.initialize(settings)
        now = _utcnow()
        with self.connect(settings) as connection:
            session = connection.execute(
                """
                SELECT id, storage_root_id, snapshot_id, files_seen
                FROM scan_session
                WHERE id = ?;
                """,
                (session_id,),
            ).fetchone()
            if session is None:
                return None
            snapshot_id = int(session["snapshot_id"])
            storage_root_id = int(session["storage_root_id"])
            zero_byte_count_row = connection.execute(
                """
                SELECT COUNT(*) AS zero_count
                FROM file_record
                WHERE storage_root_id = ?
                  AND last_seen_snapshot_id = ?
                  AND zero_byte_flag = 1;
                """,
                (storage_root_id, snapshot_id),
            ).fetchone()
            zero_byte_count = int(zero_byte_count_row["zero_count"]) if zero_byte_count_row else 0
            connection.execute(
                """
                UPDATE scan_snapshot
                SET status = 'committed',
                    committed_at = ?,
                    item_count = ?,
                    zero_byte_count = ?
                WHERE id = ?;
                """,
                (now, int(session["files_seen"]), zero_byte_count, snapshot_id),
            )
            connection.execute(
                """
                UPDATE file_record
                SET presence_status = CASE
                    WHEN last_seen_snapshot_id = ? THEN 'present'
                    ELSE 'not_seen_in_latest_snapshot'
                END
                WHERE storage_root_id = ? AND presence_status != 'quarantined';
                """,
                (snapshot_id, storage_root_id),
            )
            connection.execute(
                """
                UPDATE scan_session
                SET status = 'completed',
                    heartbeat_at = ?,
                    completed_at = ?
                WHERE id = ?;
                """,
                (now, now, session_id),
            )
            connection.commit()
        return self.get_scan_session(settings, session_id)

    def list_scan_sessions(
        self,
        settings: AppSettings,
        *,
        slug: str | None = None,
    ) -> list[dict[str, object]]:
        self.initialize(settings)
        parameters: list[object] = []
        where_clause = ""
        if slug is not None:
            where_clause = "WHERE root.slug = ?"
            parameters.append(slug)
        with self.connect(settings) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    session.id,
                    session.status,
                    session.started_at,
                    session.heartbeat_at,
                    session.completed_at,
                    session.max_files,
                    session.files_seen,
                    session.bytes_seen,
                    session.directories_completed,
                    session.error_count,
                    session.last_relative_path,
                    session.snapshot_id,
                    root.slug AS root_slug,
                    root.root_type AS root_type,
                    root.absolute_path AS root_path
                FROM scan_session AS session
                JOIN storage_root AS root
                  ON root.id = session.storage_root_id
                {where_clause}
                ORDER BY session.started_at DESC;
                """,
                tuple(parameters),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_latest_snapshots(
        self,
        settings: AppSettings,
        *,
        slug: str | None = None,
    ) -> list[dict[str, object]]:
        self.initialize(settings)
        parameters: list[object] = []
        slug_filter = ""
        if slug is not None:
            slug_filter = "AND root.slug = ?"
            parameters.append(slug)
        with self.connect(settings) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    root.slug AS root_slug,
                    root.root_type AS root_type,
                    root.absolute_path,
                    root.updated_at AS root_updated_at,
                    snapshot.id AS snapshot_id,
                    snapshot.generation,
                    snapshot.status,
                    snapshot.started_at,
                    snapshot.committed_at,
                    snapshot.item_count,
                    snapshot.zero_byte_count,
                    CASE
                        WHEN snapshot.id IS NULL THEN 0
                        WHEN snapshot.committed_at IS NOT NULL
                             AND snapshot.committed_at >= root.updated_at THEN 1
                        ELSE 0
                    END AS snapshot_current,
                    CASE
                        WHEN snapshot.id IS NULL THEN 'missing'
                        WHEN snapshot.committed_at IS NOT NULL
                             AND snapshot.committed_at < root.updated_at
                        THEN 'root_configuration_changed'
                        ELSE NULL
                    END AS stale_reason
                FROM storage_root AS root
                LEFT JOIN scan_snapshot AS snapshot
                  ON snapshot.id = (
                      SELECT inner_snapshot.id
                      FROM scan_snapshot AS inner_snapshot
                      WHERE inner_snapshot.storage_root_id = root.id
                        AND inner_snapshot.status = 'committed'
                      ORDER BY inner_snapshot.generation DESC
                      LIMIT 1
                  )
                WHERE root.enabled = 1
                {slug_filter}
                ORDER BY root.slug ASC;
                """,
                tuple(parameters),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_zero_byte_files(
        self,
        settings: AppSettings,
        *,
        slug: str | None = None,
        limit: int,
    ) -> list[dict[str, object]]:
        self.initialize(settings)
        parameters: list[object] = []
        slug_filter = ""
        if slug is not None:
            slug_filter = "AND root.slug = ?"
            parameters.append(slug)
        parameters.append(limit)
        with self.connect(settings) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    root.slug AS root_slug,
                    file.relative_path,
                    file.file_name,
                    file.extension,
                    file.size_bytes,
                    file.modified_at_fs,
                    snapshot.id AS snapshot_id,
                    snapshot.generation
                FROM file_record AS file
                JOIN storage_root AS root
                  ON root.id = file.storage_root_id
                JOIN scan_snapshot AS snapshot
                  ON snapshot.id = file.last_seen_snapshot_id
                WHERE file.zero_byte_flag = 1
                  AND snapshot.status = 'committed'
                  AND snapshot.committed_at >= root.updated_at
                  AND file.last_seen_snapshot_id = (
                      SELECT inner_snapshot.id
                      FROM scan_snapshot AS inner_snapshot
                      WHERE inner_snapshot.storage_root_id = file.storage_root_id
                        AND inner_snapshot.status = 'committed'
                        AND inner_snapshot.committed_at >= root.updated_at
                      ORDER BY inner_snapshot.generation DESC
                      LIMIT 1
                  )
                  {slug_filter}
                ORDER BY root.slug ASC, file.relative_path ASC
                LIMIT ?;
                """,
                tuple(parameters),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_latest_snapshot_files(
        self,
        settings: AppSettings,
        *,
        slug: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        self.initialize(settings)
        parameters: list[object] = []
        slug_filter = ""
        if slug is not None:
            slug_filter = "AND root.slug = ?"
            parameters.append(slug)
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ?"
            parameters.append(limit)
        with self.connect(settings) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    root.slug AS root_slug,
                    root.root_type AS root_type,
                    snapshot.id AS snapshot_id,
                    snapshot.generation,
                    file.relative_path,
                    file.parent_relative_path,
                    file.file_name,
                    file.extension,
                    file.size_bytes,
                    file.modified_at_fs,
                    file.file_type_guess,
                    file.media_class_guess,
                    file.zero_byte_flag
                FROM file_record AS file
                JOIN storage_root AS root
                  ON root.id = file.storage_root_id
                JOIN scan_snapshot AS snapshot
                  ON snapshot.id = file.last_seen_snapshot_id
                WHERE snapshot.status = 'committed'
                  AND snapshot.committed_at >= root.updated_at
                  AND file.last_seen_snapshot_id = (
                      SELECT inner_snapshot.id
                      FROM scan_snapshot AS inner_snapshot
                      WHERE inner_snapshot.storage_root_id = file.storage_root_id
                        AND inner_snapshot.status = 'committed'
                        AND inner_snapshot.committed_at >= root.updated_at
                      ORDER BY inner_snapshot.generation DESC
                      LIMIT 1
                  )
                  {slug_filter}
                ORDER BY root.slug ASC, file.relative_path ASC
                {limit_clause};
                """,
                tuple(parameters),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_pending_directories(self, settings: AppSettings, session_id: str) -> int:
        self.initialize(settings)
        with self.connect(settings) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS pending_count
                FROM scan_directory_queue
                WHERE scan_session_id = ?
                  AND status IN ('pending', 'processing');
                """,
                (session_id,),
            ).fetchone()
        return int(row["pending_count"]) if row is not None else 0

    def count_pending_collect_directories(self, settings: AppSettings, session_id: str) -> int:
        self.initialize(settings)
        with self.connect(settings) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS pending_count
                FROM scan_collect_queue
                WHERE scan_session_id = ?
                  AND status IN ('pending', 'processing');
                """,
                (session_id,),
            ).fetchone()
        return int(row["pending_count"]) if row is not None else 0

    def _ensure_schema_columns(self, connection: sqlite3.Connection) -> None:
        directory_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(scan_directory_queue);").fetchall()
        }
        if "worker_id" not in directory_columns:
            connection.execute(
                "ALTER TABLE scan_directory_queue ADD COLUMN worker_id TEXT;"
            )
        if "payload_json" not in directory_columns:
            connection.execute(
                "ALTER TABLE scan_directory_queue ADD COLUMN payload_json TEXT;"
            )
        if "payload_file_count" not in directory_columns:
            connection.execute(
                "ALTER TABLE scan_directory_queue ADD COLUMN payload_file_count INTEGER NOT NULL DEFAULT 0;"
            )
        if "payload_error_count" not in directory_columns:
            connection.execute(
                "ALTER TABLE scan_directory_queue ADD COLUMN payload_error_count INTEGER NOT NULL DEFAULT 0;"
            )
        if "payload_bytes_delta" not in directory_columns:
            connection.execute(
                "ALTER TABLE scan_directory_queue ADD COLUMN payload_bytes_delta INTEGER NOT NULL DEFAULT 0;"
            )
        if "payload_last_relative_path" not in directory_columns:
            connection.execute(
                "ALTER TABLE scan_directory_queue ADD COLUMN payload_last_relative_path TEXT;"
            )

        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table';"
            ).fetchall()
        }
        if "scan_collect_queue" not in tables:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_collect_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_session_id TEXT NOT NULL REFERENCES scan_session(id),
                    relative_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(scan_session_id, relative_path)
                );
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scan_collect_queue_session_status
                    ON scan_collect_queue(scan_session_id, status, relative_path);
                """
            )

    def get_snapshot(self, settings: AppSettings, snapshot_id: int) -> dict[str, object] | None:
        self.initialize(settings)
        with self.connect(settings) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    storage_root_id,
                    source_scan_session_id,
                    snapshot_kind,
                    generation,
                    status,
                    started_at,
                    committed_at,
                    item_count,
                    zero_byte_count
                FROM scan_snapshot
                WHERE id = ?;
                """,
                (snapshot_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def _next_generation(self, settings: AppSettings, *, storage_root_id: int) -> int:
        with self.connect(settings) as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(generation), 0) + 1 AS next_generation
                FROM scan_snapshot
                WHERE storage_root_id = ?;
                """,
                (storage_root_id,),
            ).fetchone()
        if row is None:
            return 1
        return int(row["next_generation"])


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS storage_root (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    setting_name TEXT NOT NULL,
    root_type TEXT NOT NULL,
    absolute_path TEXT NOT NULL UNIQUE,
    path_case_sensitive INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_root_id INTEGER NOT NULL REFERENCES storage_root(id),
    source_scan_session_id TEXT,
    snapshot_kind TEXT NOT NULL,
    generation INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    committed_at TEXT,
    item_count INTEGER NOT NULL DEFAULT 0,
    zero_byte_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_scan_snapshot_root_generation
    ON scan_snapshot(storage_root_id, generation DESC);

CREATE TABLE IF NOT EXISTS scan_session (
    id TEXT PRIMARY KEY,
    storage_root_id INTEGER NOT NULL REFERENCES storage_root(id),
    snapshot_id INTEGER NOT NULL REFERENCES scan_snapshot(id),
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    completed_at TEXT,
    max_files INTEGER,
    files_seen INTEGER NOT NULL DEFAULT 0,
    bytes_seen INTEGER NOT NULL DEFAULT 0,
    directories_completed INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    last_relative_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_scan_session_root_status
    ON scan_session(storage_root_id, status);

CREATE TABLE IF NOT EXISTS scan_directory_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_session_id TEXT NOT NULL REFERENCES scan_session(id),
    relative_path TEXT NOT NULL,
    status TEXT NOT NULL,
    worker_id TEXT,
    discovered_at TEXT NOT NULL,
    payload_json TEXT,
    payload_file_count INTEGER NOT NULL DEFAULT 0,
    payload_error_count INTEGER NOT NULL DEFAULT 0,
    payload_bytes_delta INTEGER NOT NULL DEFAULT 0,
    payload_last_relative_path TEXT,
    completed_at TEXT,
    UNIQUE(scan_session_id, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_scan_directory_queue_session_status
    ON scan_directory_queue(scan_session_id, status, relative_path);

CREATE TABLE IF NOT EXISTS scan_collect_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_session_id TEXT NOT NULL REFERENCES scan_session(id),
    relative_path TEXT NOT NULL,
    status TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(scan_session_id, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_scan_collect_queue_session_status
    ON scan_collect_queue(scan_session_id, status, relative_path);

CREATE TABLE IF NOT EXISTS file_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_root_id INTEGER NOT NULL REFERENCES storage_root(id),
    relative_path TEXT NOT NULL,
    parent_relative_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    extension TEXT,
    size_bytes INTEGER NOT NULL,
    created_at_fs TEXT,
    modified_at_fs TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    first_seen_snapshot_id INTEGER NOT NULL REFERENCES scan_snapshot(id),
    last_seen_snapshot_id INTEGER NOT NULL REFERENCES scan_snapshot(id),
    last_scan_session_id TEXT NOT NULL REFERENCES scan_session(id),
    file_type_guess TEXT NOT NULL,
    media_class_guess TEXT NOT NULL,
    zero_byte_flag INTEGER NOT NULL DEFAULT 0,
    stat_device TEXT,
    stat_inode TEXT,
    hash_status TEXT NOT NULL DEFAULT 'not_requested',
    content_hash TEXT,
    hash_algorithm TEXT,
    hash_last_verified_at TEXT,
    presence_status TEXT NOT NULL DEFAULT 'present',
    metadata_json TEXT,
    UNIQUE(storage_root_id, relative_path)
);

CREATE INDEX IF NOT EXISTS idx_file_record_root_snapshot
    ON file_record(storage_root_id, last_seen_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_file_record_zero_byte
    ON file_record(storage_root_id, zero_byte_flag, last_seen_snapshot_id);
"""
