\pset format csv
\pset fieldsep ','
\pset tuples_only on
\pset pager off

CREATE TEMP TABLE tmp_eav_names(
  table_schema text,
  table_name text,
  attribute_name text,
  count bigint
);

DO $$
DECLARE
  rec RECORD;
BEGIN
  FOR rec IN
    SELECT table_schema, table_name
    FROM information_schema.columns
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
      AND column_name = 'name'
      AND table_name ILIKE '%attribute%'
    GROUP BY table_schema, table_name
  LOOP
    EXECUTE format($f$
      INSERT INTO tmp_eav_names(table_schema, table_name, attribute_name, count)
      SELECT %L, %L, name, COUNT(*)::bigint
      FROM %I.%I
      GROUP BY name
      ORDER BY COUNT(*) DESC
    $f$, rec.table_schema, rec.table_name, rec.table_schema, rec.table_name);
  END LOOP;
END $$;

TABLE tmp_eav_names
ORDER BY table_schema, table_name, count DESC;
