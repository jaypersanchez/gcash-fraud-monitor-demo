"""
Export graph-like data from Postgres into Neo4j.

Tables expected (from generate_graph_data.py):
  - graph_accounts (id, account_number, customer_name, risk_score, is_fraud)
  - graph_devices (id, device_id, device_type)
  - graph_account_device (account_id, device_id)
  - graph_transactions (tx_ref, from_account_id, to_account_id, amount, channel, timestamp, is_flagged, tags)

Env vars:
  DATABASE_URL (Postgres)
  NEO4J_URI (e.g., neo4j+s://<aura-endpoint>)
  NEO4J_USER
  NEO4J_PASSWORD
"""

import os
from typing import Iterable, List, Dict
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from neo4j import GraphDatabase

BATCH_SIZE = 500


def chunk(items: Iterable[Dict], size: int):
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def create_constraints(driver):
    queries = [
        "CREATE CONSTRAINT account_account_number IF NOT EXISTS ON (a:Account) ASSERT a.account_number IS UNIQUE",
        "CREATE CONSTRAINT device_device_id IF NOT EXISTS ON (d:Device) ASSERT d.device_id IS UNIQUE",
        "CREATE CONSTRAINT tx_tx_ref IF NOT EXISTS ON (t:Transaction) ASSERT t.tx_ref IS UNIQUE",
    ]
    with driver.session() as session:
        for q in queries:
            session.run(q)


def export_accounts_devices(engine, driver):
    with engine.connect() as conn:
        accounts = conn.execute(text("SELECT account_number, customer_name, risk_score, is_fraud FROM graph_accounts")).mappings()
        devices = conn.execute(text("SELECT device_id, device_type FROM graph_devices")).mappings()
        account_device = conn.execute(
            text(
                """
                SELECT a.account_number, d.device_id
                FROM graph_account_device ad
                JOIN graph_accounts a ON a.id = ad.account_id
                JOIN graph_devices d ON d.id = ad.device_id
                """
            )
        ).mappings()

    with driver.session() as session:
        for batch in chunk(accounts, BATCH_SIZE):
            session.run(
                """
                UNWIND $batch AS row
                MERGE (a:Account {account_number: row.account_number})
                SET a.customer_name = row.customer_name,
                    a.risk_score = row.risk_score,
                    a.is_fraud = row.is_fraud
                """,
                batch=list(batch),
            )

        for batch in chunk(devices, BATCH_SIZE):
            session.run(
                """
                UNWIND $batch AS row
                MERGE (d:Device {device_id: row.device_id})
                SET d.device_type = row.device_type
                """,
                batch=list(batch),
            )

        for batch in chunk(account_device, BATCH_SIZE):
            session.run(
                """
                UNWIND $batch AS row
                MERGE (a:Account {account_number: row.account_number})
                MERGE (d:Device {device_id: row.device_id})
                MERGE (a)-[:USES]->(d)
                """,
                batch=list(batch),
            )


def export_transactions(engine, driver):
    with engine.connect() as conn:
        tx_rows = list(
            conn.execute(
            text(
                """
                SELECT t.tx_ref,
                       fa.account_number AS from_acct,
                       ta.account_number AS to_acct,
                       t.amount,
                       t.channel,
                       t.timestamp,
                       t.is_flagged,
                       t.tags
                FROM graph_transactions t
                JOIN graph_accounts fa ON fa.id = t.from_account_id
                JOIN graph_accounts ta ON ta.id = t.to_account_id
                """
            )
            ).mappings()
        )
        # Persist to transaction_logs for BSP 1213 alignment
        for row in tx_rows:
            conn.execute(
                text(
                    """
                    INSERT INTO transaction_logs (
                        tx_reference, sender_account_id, receiver_account_id,
                        amount, currency, tx_datetime, ofi, rfi, channel,
                        auth_method, device_fingerprint, device_details,
                        ip_address, browser_user_agent, non_financial_action,
                        network_reference, created_at
                    ) VALUES (
                        :tx_reference, :sender_account_id, :receiver_account_id,
                        :amount, :currency, :tx_datetime, :ofi, :rfi, :channel,
                        :auth_method, :device_fingerprint, :device_details,
                        :ip_address, :browser_user_agent, :non_financial_action,
                        :network_reference, NOW()
                    )
                    ON CONFLICT (tx_reference) DO NOTHING
                    """
                ),
                {
                    "tx_reference": row["tx_ref"],
                    "sender_account_id": row["from_acct"],
                    "receiver_account_id": row["to_acct"],
                    "amount": row["amount"],
                    "currency": "PHP",
                    "tx_datetime": row["timestamp"],
                    "ofi": "GCASH_CORE",
                    "rfi": "GCASH_CORE",
                    "channel": row["channel"],
                    "auth_method": "OTP_SMS",
                    "device_fingerprint": None,
                    "device_details": None,
                    "ip_address": None,
                    "browser_user_agent": None,
                    "non_financial_action": None,
                    "network_reference": row["tags"],
                },
            )

    with driver.session() as session:
        for batch in chunk(tx_rows, BATCH_SIZE):
            # convert datetime to iso for Aura compatibility
            payload: List[Dict] = []
            for row in batch:
                payload.append(
                    {
                        "tx_ref": row["tx_ref"],
                        "from_acct": row["from_acct"],
                        "to_acct": row["to_acct"],
                        "amount": float(row["amount"]),
                        "channel": row["channel"],
                        "timestamp": row["timestamp"].isoformat() if isinstance(row["timestamp"], datetime) else row["timestamp"],
                        "is_flagged": row["is_flagged"],
                        "tags": row["tags"],
                    }
                )
            session.run(
                """
                UNWIND $batch AS row
                MERGE (src:Account {account_number: row.from_acct})
                MERGE (dst:Account {account_number: row.to_acct})
                MERGE (tx:Transaction {tx_ref: row.tx_ref})
                SET tx.amount = row.amount,
                    tx.channel = row.channel,
                    tx.timestamp = datetime(row.timestamp),
                    tx.is_flagged = row.is_flagged,
                    tx.tags = row.tags
                MERGE (src)-[:PERFORMS]->(tx)
                MERGE (tx)-[:TO]->(dst)
                """,
                batch=payload,
            )


def main():
    load_dotenv()
    pg_url = os.getenv("DATABASE_URL")
    neo_uri = os.getenv("NEO4J_URI")
    neo_user = os.getenv("NEO4J_USER")
    neo_password = os.getenv("NEO4J_PASSWORD")

    if not all([pg_url, neo_uri, neo_user, neo_password]):
        raise SystemExit("DATABASE_URL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD are required")

    engine = create_engine(pg_url)
    driver = GraphDatabase.driver(neo_uri, auth=(neo_user, neo_password))

    try:
        create_constraints(driver)
        export_accounts_devices(engine, driver)
        export_transactions(engine, driver)
        print("Export complete.")
    finally:
        driver.close()
        engine.dispose()


if __name__ == "__main__":
    main()
