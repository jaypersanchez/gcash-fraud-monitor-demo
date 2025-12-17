#!/usr/bin/env bash
set -euo pipefail
source .env

: "${PGHOST:?PGHOST is required}"
: "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGSSLMODE:?PGSSLMODE is required}"
DBNAME="${DBNAME:-postgres}"

mkdir -p outputs/reports
OUTFILE="outputs/reports/00_connectivity.txt"

psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" -v ON_ERROR_STOP=1 \
  <<'SQL' > "$OUTFILE"
-- Connectivity + identity (read-only)
SELECT now() AS check_time;
SELECT version();
SELECT current_user AS current_user, session_user AS session_user;

-- List roles for the current user (no secrets)
SELECT current_user AS user_name, array_agg(r.rolname ORDER BY r.rolname) AS roles
FROM pg_roles r
JOIN pg_auth_members m ON m.roleid = r.oid
JOIN pg_roles u ON u.oid = m.member
WHERE u.rolname = current_user
GROUP BY current_user;
SQL

echo "Connectivity check written to $OUTFILE"
