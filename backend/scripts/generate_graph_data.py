"""
Generate mock fraud graph data in Postgres for Neo4j-style demos.

Creates/clears tables:
  - graph_accounts
  - graph_devices
  - graph_account_device (link)
  - graph_transactions

Inserts ~5k transactions across good traffic plus mule-ring and identity-fraud patterns.
"""

import os
import random
from datetime import datetime, timedelta

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    create_engine,
)


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/gcash_fraud_demo")
ENGINE = create_engine(DATABASE_URL)
metadata = MetaData()

accounts_table = Table(
    "graph_accounts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("account_number", String(50), unique=True, nullable=False),
    Column("customer_name", String(255), nullable=False),
    Column("risk_score", Float, nullable=True),
    Column("is_fraud", Boolean, default=False, nullable=False),
)

devices_table = Table(
    "graph_devices",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("device_id", String(100), unique=True, nullable=False),
    Column("device_type", String(100), nullable=True),
)

account_device_table = Table(
    "graph_account_device",
    metadata,
    Column("account_id", Integer, ForeignKey("graph_accounts.id", ondelete="CASCADE"), primary_key=True),
    Column("device_id", Integer, ForeignKey("graph_devices.id", ondelete="CASCADE"), primary_key=True),
)

transactions_table = Table(
    "graph_transactions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tx_ref", String(100), unique=True, nullable=False),
    Column("from_account_id", Integer, ForeignKey("graph_accounts.id", ondelete="CASCADE"), nullable=False),
    Column("to_account_id", Integer, ForeignKey("graph_accounts.id", ondelete="CASCADE"), nullable=False),
    Column("amount", Numeric(14, 2), nullable=False),
    Column("channel", String(50), nullable=False),
    Column("timestamp", DateTime, nullable=False),
    Column("is_flagged", Boolean, default=False, nullable=False),
    Column("tags", String(255), nullable=True),
)


def reset_tables():
    metadata.create_all(ENGINE)
    with ENGINE.begin() as conn:
        conn.execute(account_device_table.delete())
        conn.execute(transactions_table.delete())
        conn.execute(accounts_table.delete())
        conn.execute(devices_table.delete())


def make_accounts(start_id: int, count: int, prefix: str, fraud: bool = False):
    accounts = []
    for i in range(count):
        acc_id = start_id + i
        accounts.append(
            {
                "id": acc_id,
                "account_number": f"{prefix}-{acc_id:06d}",
                "customer_name": f"Customer {prefix}-{acc_id:04d}",
                "risk_score": round(random.uniform(0.1, 0.95), 2),
                "is_fraud": fraud,
            }
        )
    return accounts


def make_devices(start_id: int, count: int, prefix: str):
    devices = []
    for i in range(count):
        dev_id = start_id + i
        devices.append(
            {
                "id": dev_id,
                "device_id": f"{prefix}-{dev_id:05d}",
                "device_type": random.choice(["Android", "iOS", "Web"]),
            }
        )
    return devices


def generate_data():
    random.seed(42)
    base_time = datetime.utcnow()

    # Accounts
    mule_accounts = make_accounts(1, 80, "MULE", fraud=True)
    identity_accounts = make_accounts(201, 40, "IDFRAUD", fraud=True)
    good_accounts = make_accounts(501, 1000, "GOOD", fraud=False)
    all_accounts = mule_accounts + identity_accounts + good_accounts

    # Devices
    mule_devices = make_devices(1, 8, "MULE-DEV")
    identity_devices = make_devices(101, 5, "ID-DEV")
    good_devices = make_devices(201, 200, "GOOD-DEV")
    all_devices = mule_devices + identity_devices + good_devices

    # Account-device links
    account_device_links = []
    # Mule rings: each device links 10 mule accounts
    for idx, device in enumerate(mule_devices):
        ring_accounts = mule_accounts[idx * 10 : (idx + 1) * 10]
        for acc in ring_accounts:
            account_device_links.append({"account_id": acc["id"], "device_id": device["id"]})
    # Identity fraud pairs share devices
    for idx, device in enumerate(identity_devices):
        pair_accounts = identity_accounts[idx * 8 : (idx + 1) * 8]
        for acc in pair_accounts:
            account_device_links.append({"account_id": acc["id"], "device_id": device["id"]})
    # Good accounts get random devices
    for acc in good_accounts:
        dev = random.choice(good_devices)
        account_device_links.append({"account_id": acc["id"], "device_id": dev["id"]})

    transactions = []
    tx_id = 1

    def add_tx(from_id, to_id, amount, days_ago, flagged=False, tags=None):
        nonlocal tx_id
        transactions.append(
            {
                "id": tx_id,
                "tx_ref": f"TX-{tx_id:07d}",
                "from_account_id": from_id,
                "to_account_id": to_id,
                "amount": round(amount, 2),
                "channel": random.choice(["P2P", "Wallet", "QR", "Bills"]),
                "timestamp": base_time - timedelta(days=days_ago, minutes=random.randint(0, 1200)),
                "is_flagged": flagged,
                "tags": tags,
            }
        )
        tx_id += 1

    # Mule ring circular flows
    for ring_start in range(0, len(mule_accounts), 10):
        ring = mule_accounts[ring_start : ring_start + 10]
        for i in range(len(ring)):
            src = ring[i]["id"]
            dst = ring[(i + 1) % len(ring)]["id"]
            add_tx(src, dst, random.uniform(5000, 15000), days_ago=random.randint(0, 2), flagged=True, tags="mule_ring")
        # extra layering
        for _ in range(10):
            src = random.choice(ring)["id"]
            dst = random.choice(ring)["id"]
            if src != dst:
                add_tx(src, dst, random.uniform(2000, 8000), days_ago=random.randint(0, 3), flagged=True, tags="mule_layer")

    # Identity fraud cross-usage
    for device in identity_devices:
        shared_accounts = [link["account_id"] for link in account_device_links if link["device_id"] == device["id"]]
        for i in range(len(shared_accounts) - 1):
            add_tx(shared_accounts[i], shared_accounts[i + 1], random.uniform(500, 4000), days_ago=random.randint(0, 5), flagged=True, tags="identity_overlap")

    # Good traffic
    good_ids = [acc["id"] for acc in good_accounts]
    for _ in range(4000):
        src = random.choice(good_ids)
        dst = random.choice(good_ids)
        if src == dst:
            continue
        add_tx(src, dst, random.uniform(50, 2500), days_ago=random.randint(0, 14), flagged=False, tags="legit")

    # Top-up to ~5k transactions total
    while len(transactions) < 5000:
        src = random.choice(good_ids)
        dst = random.choice(good_ids)
        if src == dst:
            continue
        add_tx(src, dst, random.uniform(20, 3000), days_ago=random.randint(0, 20), flagged=False, tags="legit")

    return all_accounts, all_devices, account_device_links, transactions


def insert_all():
    reset_tables()
    accounts, devices, links, txs = generate_data()
    with ENGINE.begin() as conn:
        conn.execute(accounts_table.insert(), accounts)
        conn.execute(devices_table.insert(), devices)
        conn.execute(account_device_table.insert(), links)
        conn.execute(transactions_table.insert(), txs)
    print(f"Inserted accounts={len(accounts)}, devices={len(devices)}, links={len(links)}, transactions={len(txs)}")


if __name__ == "__main__":
    insert_all()
