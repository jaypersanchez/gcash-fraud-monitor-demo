\pset format aligned
\pset pager off

-- Identify top candidate tables with identifier-like columns, then emit safe metadata:
-- estimated rows, min/max timestamps, distinct status/state/type values (up to 20).
DO $$
DECLARE
  rec RECORD;
  ts_col text;
  status_cols text[];
  status_preview text;
  min_ts timestamptz;
  max_ts timestamptz;
  est_rows numeric;
BEGIN
  CREATE TEMP TABLE safe_samples(
    table_schema text,
    table_name text,
    estimated_rows numeric,
    min_timestamp timestamptz,
    max_timestamp timestamptz,
    status_values text
  ) ON COMMIT DROP;

  FOR rec IN
    SELECT DISTINCT c.table_schema, c.table_name, cls.reltuples
    FROM information_schema.columns c
    JOIN pg_class cls ON cls.relname = c.table_name
    JOIN pg_namespace ns ON ns.oid = cls.relnamespace AND ns.nspname = c.table_schema
    WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
      AND c.column_name ILIKE ANY (ARRAY[
        '%email%', '%phone%', '%mobile%', '%msisdn%', '%device%', '%imei%', '%imsi%', '%ssid%',
        '%account%number%', '%acct%', '%external%ref%', '%reference%', '%ssn%', '%sss%', '%tin%',
        '%id%number%', '%passport%', '%document%', '%paycode%', '%ip%', '%address%', '%birth%', '%dob%', '%name%'
      ])
      AND cls.relkind IN ('r','p','m')
    ORDER BY cls.reltuples DESC NULLS LAST
    LIMIT 10
  LOOP
    est_rows := rec.reltuples;

    SELECT column_name
    INTO ts_col
    FROM information_schema.columns
    WHERE table_schema = rec.table_schema
      AND table_name = rec.table_name
      AND data_type ILIKE 'timestamp%'
    ORDER BY ordinal_position
    LIMIT 1;

    IF ts_col IS NOT NULL THEN
      EXECUTE format('SELECT min(%I), max(%I) FROM %I.%I', ts_col, ts_col, rec.table_schema, rec.table_name)
      INTO min_ts, max_ts;
    ELSE
      min_ts := NULL;
      max_ts := NULL;
    END IF;

    SELECT array_agg(column_name)
    INTO status_cols
    FROM information_schema.columns
    WHERE table_schema = rec.table_schema
      AND table_name = rec.table_name
      AND column_name ILIKE ANY (ARRAY['%status%', '%state%', '%type%']);

    status_preview := NULL;
    IF status_cols IS NOT NULL THEN
      FOR ts_col IN SELECT unnest(status_cols)
      LOOP
        EXECUTE format($f$
          SELECT string_agg(val::text, ', ' ORDER BY val)
          FROM (
            SELECT DISTINCT %I AS val FROM %I.%I LIMIT 20
          ) s
        $f$, ts_col, rec.table_schema, rec.table_name)
        INTO status_preview;
        EXIT WHEN status_preview IS NOT NULL;
      END LOOP;
    END IF;

    INSERT INTO safe_samples(table_schema, table_name, estimated_rows, min_timestamp, max_timestamp, status_values)
    VALUES (rec.table_schema, rec.table_name, est_rows, min_ts, max_ts, status_preview);
  END LOOP;

END $$;

TABLE safe_samples
ORDER BY estimated_rows DESC NULLS LAST, table_schema, table_name;
