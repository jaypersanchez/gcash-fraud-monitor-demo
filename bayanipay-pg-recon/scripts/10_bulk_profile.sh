#!/usr/bin/env bash
set -euo pipefail
source .env

: "${PGHOST:?PGHOST is required}"
: "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGSSLMODE:?PGSSLMODE is required}"

export PGHOST PGPORT PGUSER PGPASSWORD PGSSLMODE

# Optional: provide a space-separated list of DBs via DB_LIST to override inventory parsing.
# Optional: set INVENTORY_FILE (defaults to outputs/inventory/01_databases.txt).
# Optional: set RUN_SCHEMA_DUMP=0 to skip schema-only dumps.
INVENTORY_FILE="${INVENTORY_FILE:-outputs/inventory/01_databases.txt}"
RUN_SCHEMA_DUMP="${RUN_SCHEMA_DUMP:-1}"

mkdir -p outputs/schemas outputs/erd outputs/reports

parse_inventory() {
  if [[ ! -f "$INVENTORY_FILE" ]]; then
    echo "Inventory file not found: $INVENTORY_FILE" >&2
    exit 1
  fi
  # Expect pipe-delimited columns: datname | owner | size | datistemplate
  awk -F '|' '
    NF >= 4 {
      db=$1; tmpl=$4;
      gsub(/^ +| +$/, "", db);
      gsub(/^ +| +$/, "", tmpl);
      if (db != "" && db != "datname" && tmpl != "t") print db;
    }
  ' "$INVENTORY_FILE"
}

DBS=()
if [[ -n "${DB_LIST:-}" ]]; then
  for db in $DB_LIST; do
    DBS+=("$db")
  done
else
  while IFS= read -r db; do
    [[ -n "$db" ]] && DBS+=("$db")
  done < <(parse_inventory)
fi

if [[ ${#DBS[@]} -eq 0 ]]; then
  echo "No databases to process." >&2
  exit 1
fi

echo "Processing ${#DBS[@]} database(s): ${DBS[*]}"

for DBNAME in "${DBS[@]}"; do
  echo "==> ${DBNAME}"
  # Profiling
  psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" \
    -f scripts/03_table_profiling.sql > "outputs/schemas/${DBNAME}_profiling.txt"

  # Foreign key graph (CSV)
  psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" \
    -f scripts/04_fk_graph.sql > "outputs/erd/${DBNAME}_fk.csv"

  # High-value entities scan
  psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" \
    -f scripts/05_high_value_entities.sql > "outputs/reports/${DBNAME}_high_value_scan.txt"

  if [[ "$RUN_SCHEMA_DUMP" != "0" ]]; then
    DBNAME="$DBNAME" bash scripts/02_schema_dump.sh
  fi

done

echo "Bulk profiling complete."
