\pset format aligned
\pset pager off

WITH fks AS (
  SELECT
    con.conname AS fk_name,
    src_n.nspname AS source_schema,
    src_c.relname AS source_table,
    array_agg(src_a.attname ORDER BY k.ord) AS source_cols,
    tgt_n.nspname AS target_schema,
    tgt_c.relname AS target_table,
    array_agg(tgt_a.attname ORDER BY k.ord) AS target_cols
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
    AND (src_c.relname ILIKE ANY (ARRAY[
          '%account%', '%device%', '%party%', '%external_account%', '%funding%',
          '%payment%', '%transaction%', '%state%'
        ])
      OR tgt_c.relname ILIKE ANY (ARRAY[
          '%account%', '%device%', '%party%', '%external_account%', '%funding%',
          '%payment%', '%transaction%', '%state%'
        ]))
  GROUP BY con.conname, src_n.nspname, src_c.relname, tgt_n.nspname, tgt_c.relname
)
SELECT
  format('%s.%s(%s) -> %s.%s(%s)  [%s]',
         source_schema, source_table, array_to_string(source_cols, ','),
         target_schema, target_table, array_to_string(target_cols, ','),
         fk_name) AS link_path
FROM fks
ORDER BY source_schema, source_table, fk_name;
