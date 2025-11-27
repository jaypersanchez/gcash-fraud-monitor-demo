"""
Export graph_* tables from Postgres to CSV files for Neo4j Data Importer.

Outputs (relative to backend/):
  data/accounts.csv
  data/devices.csv
  data/transactions.csv
  data/account_device.csv
"""

import csv
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


def ensure_data_dir_exists():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _row_to_list(row, columns):
    processed = []
    for col in columns:
        val = row[col]
        if isinstance(val, datetime):
            processed.append(val.isoformat())
        else:
            processed.append(val)
    return processed


def export_accounts(conn):
    query = text(
        """
        SELECT
          id,
          account_number,
          customer_name,
          risk_score,
          is_fraud
        FROM graph_accounts
        """
    )
    headers = ["id", "account_number", "customer_name", "risk_score", "is_fraud"]
    path = DATA_DIR / "accounts.csv"
    result = conn.execute(query).mappings()
    rows = list(result)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(_row_to_list(row, headers))
    print(f"Wrote {len(rows)} rows to {path}")


def export_devices(conn):
    query = text(
        """
        SELECT
          id,
          device_id,
          device_type
        FROM graph_devices
        """
    )
    headers = ["id", "device_id", "device_type"]
    path = DATA_DIR / "devices.csv"
    result = conn.execute(query).mappings()
    rows = list(result)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(_row_to_list(row, headers))
    print(f"Wrote {len(rows)} rows to {path}")


def export_transactions(conn):
    query = text(
        """
        SELECT
          id,
          tx_ref,
          from_account_id,
          to_account_id,
          amount,
          channel,
          "timestamp",
          is_flagged,
          tags
        FROM graph_transactions
        """
    )
    headers = ["id", "tx_ref", "from_account_id", "to_account_id", "amount", "channel", "timestamp", "is_flagged", "tags"]
    path = DATA_DIR / "transactions.csv"
    result = conn.execute(query).mappings()
    rows = list(result)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(_row_to_list(row, headers))
    print(f"Wrote {len(rows)} rows to {path}")


def export_account_device(conn):
    query = text(
        """
        SELECT
          account_id,
          device_id
        FROM graph_account_device
        """
    )
    headers = ["account_id", "device_id"]
    path = DATA_DIR / "account_device.csv"
    result = conn.execute(query).mappings()
    rows = list(result)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(_row_to_list(row, headers))
    print(f"Wrote {len(rows)} rows to {path}")


def main():
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL is required in .env")

    engine = create_engine(db_url)
    ensure_data_dir_exists()

    with engine.connect() as conn:
        export_accounts(conn)
        export_devices(conn)
        export_transactions(conn)
        export_account_device(conn)


if __name__ == "__main__":
    main()
