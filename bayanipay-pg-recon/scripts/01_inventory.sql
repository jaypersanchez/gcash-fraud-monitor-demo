\pset pager off
\timing on

-- Database inventory (run against postgres)
SELECT datname AS database,
       pg_catalog.pg_get_userbyid(datdba) AS owner,
       pg_size_pretty(pg_database_size(datname)) AS size,
       pg_encoding_to_char(encoding) AS encoding,
       datcollate AS collate,
       datctype AS ctype,
       datistemplate AS is_template,
       datallowconn AS allow_connections,
       pg_catalog.age(datfrozenxid) AS frozenxid_age
FROM pg_database
ORDER BY datistemplate, datname;
