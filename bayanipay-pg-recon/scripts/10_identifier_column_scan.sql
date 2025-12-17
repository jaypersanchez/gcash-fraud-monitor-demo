\pset format csv
\pset fieldsep ','
\pset tuples_only on
\pset pager off

WITH patterns AS (
  SELECT unnest(ARRAY[
    '%email%', '%phone%', '%mobile%', '%msisdn%', '%device%', '%imei%', '%imsi%', '%ssid%',
    '%account%number%', '%acct%', '%external%ref%', '%reference%', '%ssn%', '%sss%', '%tin%', '%id%number%',
    '%passport%', '%document%', '%paycode%', '%ip%', '%address%', '%birth%', '%dob%', '%name%'
  ]) AS pattern
)
SELECT n.nspname AS table_schema,
       c.relname AS table_name,
       a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS data_type
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND c.relkind IN ('r','p','m')
  AND EXISTS (
    SELECT 1 FROM patterns p
    WHERE a.attname ILIKE p.pattern
  )
ORDER BY table_schema, table_name, column_name;
