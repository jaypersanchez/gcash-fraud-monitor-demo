# BayaniPay Postgres Recon (Read-Only)

Purpose: inventory and document the remote BayaniPay Postgres environment for Fraud Recon mapping. **Strictly read-only. No schema changes, no data writes.**

## Non-negotiable security rules
- Never hardcode credentials. Load from `.env` only; `.env` stays local and untracked.
- Do not echo secrets to stdout or logs.
- All scripts start with `set -euo pipefail` and `source .env`.
- Every `psql`/`pg_dump` call uses environment variables (`$PGHOST`, `$PGPORT`, `$PGUSER`, `$PGPASSWORD`, `$PGSSLMODE`, `$DBNAME`).
- If env vars are missing, scripts must fail.
- **Do not paste passwords into chat or commits. Treat creds like a live grenade with feelings.**

## Directory layout
```
bayanipay-pg-recon/
  .env.example           # template only (safe to commit)
  .gitignore             # ignores .env and outputs
  README.md              # this file
  outputs/               # all reports and dumps (ignored)
    inventory/
    schemas/
    samples/
    erd/
    mapping/
    reports/
  scripts/
    00_check_connectivity.sh
    01_inventory.sql
    02_schema_dump.sh
    03_table_profiling.sql
    04_fk_graph.sql
    05_high_value_entities.sql
    06_mapping_template.md
    10_bulk_profile.sh           # optional bulk runner
    10_identifier_column_scan.sql
    11_eav_name_scan.sql
    12_jsonb_key_scan.sql
    13_link_path_discovery.sql
    14_safe_samples.sql
    11_generate_erd_diagrams.sh
    12_generate_erd_with_columns.sh
  outputs/identifiers/      # identifier recon outputs (ignored)
```

## Quick start (read-only)
1. Create `.env` (do **not** commit):
   ```bash
   cp .env.example .env
   # edit with real credentials (do not paste into chat or code)
   ```
2. Connectivity check (defaults to `postgres` DB unless `DBNAME` is set):
   ```bash
   cd bayanipay-pg-recon
   bash scripts/00_check_connectivity.sh
   ```
   Output: `outputs/reports/00_connectivity.txt`
3. Database inventory (runs against `postgres`):
   ```bash
   DBNAME=postgres psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" \
     -f scripts/01_inventory.sql > outputs/inventory/01_databases.txt
   ```
4. For each target DB (example `core_db`):
   - Schema-only dump: `DBNAME=core_db bash scripts/02_schema_dump.sh`
   - Profiling: `DBNAME=core_db psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" -f scripts/03_table_profiling.sql > outputs/schemas/core_db_profiling.txt`
   - Foreign keys CSV/graph: `DBNAME=core_db psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" -f scripts/04_fk_graph.sql > outputs/erd/core_db_fk.csv`
   - High-value entity scan: `DBNAME=core_db psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" -f scripts/05_high_value_entities.sql > outputs/reports/core_db_high_value_scan.txt`
5. Identifier recon (per DB):
   ```bash
   DBNAME=core_db psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" -f scripts/10_identifier_column_scan.sql > outputs/identifiers/core_db_identifier_columns.csv
   DBNAME=core_db psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" -f scripts/11_eav_name_scan.sql > outputs/identifiers/core_db_eav_names.csv
   DBNAME=core_db psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" -f scripts/12_jsonb_key_scan.sql > outputs/identifiers/core_db_jsonb_keys.csv
   DBNAME=core_db psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" -f scripts/13_link_path_discovery.sql > outputs/identifiers/core_db_link_paths.txt
   DBNAME=core_db psql "host=$PGHOST port=$PGPORT user=$PGUSER dbname=$DBNAME sslmode=$PGSSLMODE" -f scripts/14_safe_samples.sql > outputs/identifiers/core_db_samples_redacted.txt
   ```

## Notes
- All outputs stay under `outputs/` (git-ignored).
- Sampling (if ever needed) must be limited (≤10 rows) and avoid PII; add ad-hoc scripts under `outputs/samples/` but keep read-only posture.
- Use `06_mapping_template.md` to draft Neo4j node/edge mapping once metadata is collected.
