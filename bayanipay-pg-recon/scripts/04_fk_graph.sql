\pset format unaligned
\pset fieldsep ','
\pset tuples_only on

-- Foreign key edges for graph export (CSV)
SELECT src_n.nspname AS source_schema,
       src_c.relname AS source_table,
       array_to_string(array_agg(src_a.attname ORDER BY k.ord), ';') AS source_columns,
       tgt_n.nspname AS target_schema,
       tgt_c.relname AS target_table,
       array_to_string(array_agg(tgt_a.attname ORDER BY k.ord), ';') AS target_columns,
       con.conname AS constraint_name
FROM pg_constraint con
JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
JOIN pg_class src_c ON src_c.oid = con.conrelid
JOIN pg_namespace src_n ON src_n.oid = src_c.relnamespace
JOIN pg_attribute src_a ON src_a.attrelid = con.conrelid AND src_a.attnum = k.attnum
JOIN pg_class tgt_c ON tgt_c.oid = con.confrelid
JOIN pg_namespace tgt_n ON tgt_n.oid = tgt_c.relnamespace
JOIN pg_attribute tgt_a ON tgt_a.attrelid = con.confrelid AND tgt_a.attnum = con.confkey[k.ord]
WHERE con.contype = 'f'
  AND src_n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY src_n.nspname, src_c.relname, tgt_n.nspname, tgt_c.relname, con.conname
ORDER BY src_n.nspname, src_c.relname, con.conname;
