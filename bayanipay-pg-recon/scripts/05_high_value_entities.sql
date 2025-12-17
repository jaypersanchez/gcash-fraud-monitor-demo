\pset pager off
\timing on

WITH tables AS (
  SELECT table_schema, table_name
  FROM information_schema.tables
  WHERE table_type = 'BASE TABLE'
    AND table_schema NOT IN ('pg_catalog', 'information_schema')
)
-- Tables flagged by name
SELECT 'table_name_match' AS match_type,
       t.table_schema,
       t.table_name,
       NULL AS column_name,
       NULL AS data_type,
       m.pattern AS matched_on
FROM tables t
JOIN (VALUES
        ('account'),('wallet'),('customer'),('user'),('device'),('session'),('ip'),
        ('merchant'),('beneficiary'),('payout'),('transfer'),('payment'),('transaction'),
        ('fraud'),('risk'),('alert'),('case'),('dispute'),('kyc'),('sanction'),('watch'),('flag')
     ) AS m(pattern)
  ON t.table_name ILIKE '%' || m.pattern || '%'

UNION ALL

-- Columns flagged by name
SELECT 'column_name_match' AS match_type,
       c.table_schema,
       c.table_name,
       c.column_name,
       c.data_type,
       m.pattern AS matched_on
FROM information_schema.columns c
JOIN (VALUES
        ('account'),('wallet'),('customer'),('user'),('device'),('session'),('ip'),
        ('merchant'),('beneficiary'),('payout'),('transfer'),('payment'),('transaction'),
        ('fraud'),('risk'),('alert'),('case'),('dispute'),('kyc'),('sanction'),('watch'),('flag'),
        ('pan'),('token'),('fingerprint'),('imei'),('imsi'),('msisdn'),('email'),('phone')
     ) AS m(pattern)
  ON c.table_schema NOT IN ('pg_catalog', 'information_schema')
 AND c.table_name NOT LIKE 'pg_%'
 AND c.column_name ILIKE '%' || m.pattern || '%'
ORDER BY match_type, table_schema, table_name, column_name NULLS FIRST;
