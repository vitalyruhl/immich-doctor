from __future__ import annotations

LIST_ALL_INDEXES_QUERY = """
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
ORDER BY schemaname, tablename, indexname;
"""

LIST_INVALID_INDEXES_QUERY = """
SELECT
    indexrelid::regclass::text AS index_name,
    indisvalid,
    indisready
FROM pg_index
WHERE NOT indisvalid OR NOT indisready
ORDER BY indexrelid::regclass::text;
"""

LIST_INDEX_USAGE_STATS_QUERY = """
SELECT
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC, relname ASC, indexrelname ASC;
"""

LIST_INDEX_SIZES_QUERY = """
SELECT
    indexrelname AS index_name,
    relname AS table_name,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC, relname ASC, indexrelname ASC;
"""

LIST_MISSING_FK_INDEXES_QUERY = """
SELECT
    conrelid::regclass::text AS table_name,
    conname,
    pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE contype = 'f'
AND conindid = 0
ORDER BY conrelid::regclass::text, conname;
"""

LIST_BASE_TABLES_QUERY = """
SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema ASC, table_name ASC;
"""

LIST_TABLE_COLUMNS_QUERY = """
SELECT
    table_schema,
    table_name,
    column_name,
    ordinal_position
FROM information_schema.columns
WHERE table_schema = %s
AND table_name = %s
ORDER BY ordinal_position ASC;
"""

LIST_TABLE_FOREIGN_KEYS_QUERY = """
SELECT
    source_ns.nspname AS table_schema,
    source_cls.relname AS table_name,
    constraint_def.conname AS constraint_name,
    target_ns.nspname AS referenced_table_schema,
    target_cls.relname AS referenced_table_name,
    CASE constraint_def.confdeltype
        WHEN 'a' THEN 'NO ACTION'
        WHEN 'r' THEN 'RESTRICT'
        WHEN 'c' THEN 'CASCADE'
        WHEN 'n' THEN 'SET NULL'
        WHEN 'd' THEN 'SET DEFAULT'
        ELSE 'UNKNOWN'
    END AS delete_action,
    array_agg(source_att.attname ORDER BY key_map.ordinality) AS column_names,
    array_agg(target_att.attname ORDER BY key_map.ordinality) AS referenced_column_names
FROM pg_constraint AS constraint_def
JOIN pg_class AS source_cls
    ON source_cls.oid = constraint_def.conrelid
JOIN pg_namespace AS source_ns
    ON source_ns.oid = source_cls.relnamespace
JOIN pg_class AS target_cls
    ON target_cls.oid = constraint_def.confrelid
JOIN pg_namespace AS target_ns
    ON target_ns.oid = target_cls.relnamespace
JOIN unnest(constraint_def.conkey, constraint_def.confkey) WITH ORDINALITY AS key_map(
    source_attnum,
    target_attnum,
    ordinality
) ON TRUE
JOIN pg_attribute AS source_att
    ON source_att.attrelid = source_cls.oid
    AND source_att.attnum = key_map.source_attnum
JOIN pg_attribute AS target_att
    ON target_att.attrelid = target_cls.oid
    AND target_att.attnum = key_map.target_attnum
WHERE constraint_def.contype = 'f'
AND source_ns.nspname = %s
AND source_cls.relname = %s
GROUP BY
    source_ns.nspname,
    source_cls.relname,
    constraint_def.conname,
    target_ns.nspname,
    target_cls.relname,
    constraint_def.confdeltype
ORDER BY constraint_def.conname ASC;
"""

READ_PG_STATISTIC_TOAST_QUERY = """
SELECT stavalues1
FROM pg_catalog.pg_statistic
WHERE stavalues1 IS NOT NULL
LIMIT 1;
"""

CURRENT_DATABASE_NAME_QUERY = """
SELECT current_database() AS database_name;
"""

CURRENT_ROLE_CAPABILITIES_QUERY = """
SELECT
    current_user AS current_user,
    session_user AS session_user,
    role.rolsuper AS is_superuser
FROM pg_roles AS role
WHERE role.rolname = current_user;
"""

ACTIVE_NON_IDLE_SESSIONS_QUERY = """
SELECT COUNT(*) AS session_count
FROM pg_stat_activity
WHERE datname = current_database()
AND pid <> pg_backend_pid()
AND state IS DISTINCT FROM 'idle';
"""

LIST_INVALID_SYSTEM_INDEXES_QUERY = """
SELECT
    table_ns.nspname AS schema_name,
    index_cls.relname AS index_name,
    table_cls.relname AS table_name,
    idx.indisvalid,
    idx.indisready
FROM pg_index AS idx
JOIN pg_class AS index_cls
    ON index_cls.oid = idx.indexrelid
JOIN pg_class AS table_cls
    ON table_cls.oid = idx.indrelid
JOIN pg_namespace AS table_ns
    ON table_ns.oid = table_cls.relnamespace
WHERE table_ns.nspname = 'pg_catalog'
AND (NOT idx.indisvalid OR NOT idx.indisready)
ORDER BY table_cls.relname ASC, index_cls.relname ASC;
"""

LIST_INVALID_USER_INDEXES_QUERY = """
SELECT
    table_ns.nspname AS schema_name,
    index_cls.relname AS index_name,
    table_cls.relname AS table_name,
    idx.indisvalid,
    idx.indisready
FROM pg_index AS idx
JOIN pg_class AS index_cls
    ON index_cls.oid = idx.indexrelid
JOIN pg_class AS table_cls
    ON table_cls.oid = idx.indrelid
JOIN pg_namespace AS table_ns
    ON table_ns.oid = table_cls.relnamespace
WHERE table_ns.nspname NOT IN ('pg_catalog', 'information_schema')
AND (NOT idx.indisvalid OR NOT idx.indisready)
ORDER BY table_cls.relname ASC, index_cls.relname ASC;
"""

LIST_DUPLICATE_ASSET_CHECKSUM_GROUPS_QUERY = """
SELECT
    "ownerId"::text AS owner_id,
    encode(checksum, 'hex') AS checksum_hex,
    COUNT(*) AS row_count,
    GREATEST(COUNT(*) - 1, 0) AS excess_row_count
FROM public.asset
WHERE checksum IS NOT NULL
GROUP BY "ownerId", checksum
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC, "ownerId"::text ASC, encode(checksum, 'hex') ASC;
"""

LIST_DUPLICATE_ASSET_CHECKSUM_ROWS_QUERY = """
SELECT
    id::text AS id,
    "ownerId"::text AS owner_id,
    encode(checksum, 'hex') AS checksum_hex,
    "originalPath" AS original_path,
    "originalFileName" AS original_file_name,
    "createdAt"::text AS created_at,
    "updatedAt"::text AS updated_at
FROM public.asset
WHERE checksum IS NOT NULL
AND ("ownerId", checksum) IN (
    SELECT "ownerId", checksum
    FROM public.asset
    WHERE checksum IS NOT NULL
    GROUP BY "ownerId", checksum
    HAVING COUNT(*) > 1
)
ORDER BY encode(checksum, 'hex') ASC, "createdAt" ASC, id ASC;
"""

LIST_ASSET_REFERENCING_FOREIGN_KEYS_QUERY = """
SELECT
    constraint_def.conname AS constraint_name,
    source_ns.nspname AS referencing_schema,
    source_cls.relname AS referencing_table,
    array_to_string(
        array_agg(source_att.attname ORDER BY key_map.ordinality),
        ','
    ) AS referencing_column,
    CASE constraint_def.confdeltype
        WHEN 'a' THEN 'NO ACTION'
        WHEN 'r' THEN 'RESTRICT'
        WHEN 'c' THEN 'CASCADE'
        WHEN 'n' THEN 'SET NULL'
        WHEN 'd' THEN 'SET DEFAULT'
        ELSE 'UNKNOWN'
    END AS cascade_rule
FROM pg_constraint AS constraint_def
JOIN pg_class AS source_cls
    ON source_cls.oid = constraint_def.conrelid
JOIN pg_namespace AS source_ns
    ON source_ns.oid = source_cls.relnamespace
JOIN pg_class AS target_cls
    ON target_cls.oid = constraint_def.confrelid
JOIN pg_namespace AS target_ns
    ON target_ns.oid = target_cls.relnamespace
JOIN unnest(constraint_def.conkey, constraint_def.confkey) WITH ORDINALITY AS key_map(
    source_attnum,
    target_attnum,
    ordinality
) ON TRUE
JOIN pg_attribute AS source_att
    ON source_att.attrelid = source_cls.oid
    AND source_att.attnum = key_map.source_attnum
JOIN pg_attribute AS target_att
    ON target_att.attrelid = target_cls.oid
    AND target_att.attnum = key_map.target_attnum
WHERE constraint_def.contype = 'f'
AND target_ns.nspname = 'public'
AND target_cls.relname = 'asset'
GROUP BY
    constraint_def.conname,
    source_ns.nspname,
    source_cls.relname,
    constraint_def.confdeltype
ORDER BY source_ns.nspname ASC, source_cls.relname ASC, constraint_def.conname ASC;
"""
