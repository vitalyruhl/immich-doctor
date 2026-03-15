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
    target_cls.relname
ORDER BY constraint_def.conname ASC;
"""
