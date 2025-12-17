\pset pager off
\timing on

-- Schemas
SELECT n.nspname AS schema_name
FROM pg_namespace n
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
ORDER BY 1;

-- Tables with estimated row counts and sizes
SELECT n.nspname AS schema_name,
       c.relname AS table_name,
       CASE c.relkind WHEN 'p' THEN 'partitioned' WHEN 'm' THEN 'materialized_view' ELSE 'table' END AS kind,
       c.reltuples::BIGINT AS estimated_rows,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
       pg_size_pretty(pg_relation_size(c.oid)) AS table_size
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p','m')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
ORDER BY pg_total_relation_size(c.oid) DESC;

-- Columns
SELECT table_schema,
       table_name,
       column_name,
       data_type,
       is_nullable,
       column_default
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;

-- Primary keys
SELECT n.nspname AS schema_name,
       c.relname AS table_name,
       a.attname AS column_name
FROM pg_index i
JOIN pg_class c ON c.oid = i.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
WHERE i.indisprimary
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schema_name, table_name, a.attnum;

-- Foreign keys
SELECT con.conname AS fk_name,
       src_n.nspname AS source_schema,
       src_c.relname AS source_table,
       array_agg(src_a.attname ORDER BY k.colid) AS source_columns,
       tgt_n.nspname AS target_schema,
       tgt_c.relname AS target_table,
       array_agg(tgt_a.attname ORDER BY k.colid) AS target_columns
FROM pg_constraint con
JOIN LATERAL unnest(con.conkey, con.confkey) WITH ORDINALITY AS k(colid, ord) ON true
JOIN pg_class src_c ON src_c.oid = con.conrelid
JOIN pg_namespace src_n ON src_n.oid = src_c.relnamespace
JOIN pg_attribute src_a ON src_a.attrelid = con.conrelid AND src_a.attnum = k.colid
JOIN pg_class tgt_c ON tgt_c.oid = con.confrelid
JOIN pg_namespace tgt_n ON tgt_n.oid = tgt_c.relnamespace
JOIN pg_attribute tgt_a ON tgt_a.attrelid = con.confrelid AND tgt_a.attnum = con.confkey[k.ord]
WHERE con.contype = 'f'
  AND src_n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY con.conname, src_n.nspname, src_c.relname, tgt_n.nspname, tgt_c.relname
ORDER BY src_n.nspname, src_c.relname, con.conname;

-- Indexes
SELECT schemaname,
       tablename,
       indexname,
       indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
