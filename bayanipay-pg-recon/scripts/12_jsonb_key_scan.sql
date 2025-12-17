\pset format csv
\pset fieldsep ','
\pset tuples_only on
\pset pager off

CREATE TEMP TABLE tmp_jsonb_keys(
  table_schema text,
  table_name text,
  column_name text,
  key text,
  count bigint
);

DO $$
DECLARE
  rec RECORD;
BEGIN
  FOR rec IN
    SELECT table_schema, table_name, column_name
    FROM information_schema.columns
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
      AND data_type = 'jsonb'
  LOOP
    EXECUTE format($f$
      INSERT INTO tmp_jsonb_keys(table_schema, table_name, column_name, key, count)
      SELECT %L, %L, %L, key, COUNT(*)::bigint
      FROM %I.%I, LATERAL jsonb_object_keys(%I) AS key
      GROUP BY key
      ORDER BY COUNT(*) DESC
      LIMIT 200
    $f$, rec.table_schema, rec.table_name, rec.column_name, rec.table_schema, rec.table_name, rec.column_name);
  END LOOP;
END $$;

TABLE tmp_jsonb_keys
ORDER BY table_schema, table_name, column_name, count DESC;
