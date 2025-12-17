#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .env

: "${PGHOST:?PGHOST is required}"
: "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGSSLMODE:?PGSSLMODE is required}"

export PGHOST PGPORT PGUSER PGPASSWORD PGSSLMODE

# DB list: space-separated via DB_LIST, otherwise parse inventory (non-template DBs)
INVENTORY_FILE="${INVENTORY_FILE:-outputs/inventory/01_databases.txt}"

parse_inventory() {
  awk -F'|' '
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
  echo "No databases specified or found." >&2
  exit 1
fi

mkdir -p outputs/erd/diagrams_with_cols

for DBNAME in "${DBS[@]}"; do
  echo "Generating ERD with columns for $DBNAME"
  OUT_BASE="outputs/erd/diagrams_with_cols/${DBNAME}_erd"
  OUT_PUML="${OUT_BASE}.puml"

  {
    echo "@startuml"
    echo "skinparam linetype ortho"
    echo "hide circle"
    echo "left to right direction"

    # Entities with columns (PK marked with *)
    psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" -A -F '|' -t <<'SQL' |
WITH pk AS (
  SELECT n.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name
  FROM pg_index i
  JOIN pg_class c ON c.oid = i.indrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
  WHERE i.indisprimary
)
SELECT n.nspname AS schema_name,
       c.relname AS table_name,
       a.attnum AS attnum,
       a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS data_type,
       CASE WHEN EXISTS (
         SELECT 1 FROM pk p
         WHERE p.schema_name = n.nspname
           AND p.table_name = c.relname
           AND p.column_name = a.attname
       ) THEN '*' ELSE '' END AS is_pk
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
WHERE c.relkind IN ('r','p','m')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname, a.attnum;
SQL
    awk -F'|' '
      {
        schema=$1; table=$2; col=$4; dtype=$5; ispk=$6;
        tbl=schema "." table;
        if (tbl != current) {
          if (current != "") { print "}"; }
          print "entity \"" tbl "\" {";
          current=tbl;
        }
        prefix=(ispk=="*") ? "*" : " ";
        printf("  %s%s : %s\n", prefix, col, dtype);
      }
      END { if (current != "") print "}" }
    '

    # FK edges from CSV
    if [[ -f "outputs/erd/${DBNAME}_fk.csv" ]]; then
      awk -F',' '
        $0 ~ /^Output format/ {next}
        $0 ~ /^Field separator/ {next}
        NF == 7 {
          for(i=1;i<=7;i++){ gsub(/^ +| +$/,"",$i) }
          src=$1 "." $2; tgt=$4 "." $5; label=$7;
          printf("\"%s\" --> \"%s\" : %s\n", src, tgt, label);
        }
      ' "outputs/erd/${DBNAME}_fk.csv"
    fi

    echo "@enduml"
  } > "$OUT_PUML"

  plantuml "$OUT_PUML" >/dev/null
done

echo "ERD diagrams with columns written under outputs/erd/diagrams_with_cols"
