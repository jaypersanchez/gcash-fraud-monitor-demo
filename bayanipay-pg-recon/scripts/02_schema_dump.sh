#!/usr/bin/env bash
set -euo pipefail
source .env

: "${PGHOST:?PGHOST is required}"
: "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGSSLMODE:?PGSSLMODE is required}"
: "${DBNAME:?DBNAME is required (target database)}"

mkdir -p outputs/schemas
OUTFILE="outputs/schemas/${DBNAME}_schema.sql"

pg_dump \
  --schema-only \
  --no-owner \
  --no-privileges \
  --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$DBNAME" --sslmode="$PGSSLMODE" \
  > "$OUTFILE"

echo "Schema-only dump written to $OUTFILE"
