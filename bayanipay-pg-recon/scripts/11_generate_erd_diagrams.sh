#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p outputs/erd/diagrams

for csv in outputs/erd/*_fk.csv; do
  [ -f "$csv" ] || continue
  base=$(basename "$csv" _fk.csv)
  out="outputs/erd/diagrams/${base}_fk.puml"
  echo "Building $out"
  {
    echo "@startuml"
    echo "skinparam linetype ortho"
    echo "hide circle"
    echo "left to right direction"
    # Skip psql pset headers; expect 7 columns.
    awk -F',' '
      $0 ~ /^Output format/ {next}
      $0 ~ /^Field separator/ {next}
      NF == 7 {
        gsub(/^ +| +$/, "", $1); gsub(/^ +| +$/, "", $2);
        gsub(/^ +| +$/, "", $4); gsub(/^ +| +$/, "", $5);
        src=$1 "." $2; tgt=$4 "." $5; label=$7;
        gsub(/^ +| +$/, "", src); gsub(/^ +| +$/, "", tgt); gsub(/^ +| +$/, "", label);
        printf("\"%s\" --> \"%s\" : %s\n", src, tgt, label);
      }
    ' "$csv"
    echo "@enduml"
  } > "$out"
  plantuml "$out" >/dev/null
done

echo "Diagrams written under outputs/erd/diagrams"
