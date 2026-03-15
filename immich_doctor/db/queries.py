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
