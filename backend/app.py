import os
import sys
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import select, text
from neo4j import GraphDatabase

# Ensure project root is on sys.path when running directly from backend/
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import Config
from backend.db.session import engine, get_session
from backend.models import Base, RuleDefinition, Account, Device
from backend.models.investigator_action import InvestigatorAction
from backend.routes.alerts import alerts_bp
from backend.routes.cases import cases_bp
from backend.routes.rules import rules_bp
from backend.routes.neo4j import neo4j_bp
from backend.routes.investigator import investigator_bp

# Neo4j driver (global)
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
driver = None
if all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def is_locally_flagged(anchor_id: str, anchor_type: str) -> bool:
    session = get_session()
    try:
        exists = (
            session.query(InvestigatorAction)
            .filter(
                InvestigatorAction.anchor_id == anchor_id,
                InvestigatorAction.anchor_type == anchor_type,
                InvestigatorAction.action == "FLAG",
            )
            .first()
            is not None
        )
        return exists
    finally:
        session.close()


def is_flagged_record(rec: dict, anchor_type: str) -> bool:
    anchor_id = rec.get("accountId") or rec.get("deviceId")
    if not anchor_id:
        return False
    if str(rec.get("isFraud")).lower() == "true":
        return True
    return is_locally_flagged(anchor_id, anchor_type)
def fetch_account_alerts(tx, min_risk: float):
    """
    Xavier data uses :Mule to represent flagged accounts.
    Return them as high-risk accounts (riskScore forced to 1.0).
    """
    cypher = """
    MATCH (a:Mule)
    RETURN
      a.id   AS accountId,
      a.name AS customerName,
      1.0    AS riskScore,
      true   AS isFraud
    ORDER BY accountId
    LIMIT 100
    """
    result = tx.run(cypher, minRisk=min_risk)
    return [record.data() for record in result]


def fetch_account_alerts_r1(tx, min_risk: float, limit: int):
    """
    R1 for Xavier: treat all :Mule nodes as flagged/high-risk accounts.
    We expose a fixed riskScore (1.0) and ignore min_risk because the dataset
    does not store risk on Client/Mule nodes.
    """
    cypher = """
    MATCH (a:Mule)
    RETURN
      a.id   AS accountId,
      a.name AS customerName,
      1.0    AS riskScore,
      true   AS isFraud
    ORDER BY accountId
    LIMIT $limit
    """
    result = tx.run(cypher, minRisk=min_risk, limit=limit)
    return [record.data() for record in result]


def fetch_device_alerts_r2(tx, high_risk: float, min_risky: int, limit: int):
    """
    Xavier data has no Device nodes; use shared identifiers (Email/Phone/SSN) across mules.
    Treat any identifier connected to >= min_risky Mule nodes as a risky hub.
    """
    cypher = """
    MATCH (id)<-[:HAS_EMAIL|HAS_PHONE|HAS_SSN]-(risky:Mule)
    WITH id, collect(DISTINCT risky) AS riskyAccounts, count(DISTINCT risky) AS riskyCount
    MATCH (id)<-[:HAS_EMAIL|HAS_PHONE|HAS_SSN]-(acc)
    WITH id, riskyCount, collect(DISTINCT acc) AS allAccounts
    WHERE riskyCount >= $minRiskyAccounts
    RETURN
      CASE
        WHEN id.email IS NOT NULL THEN id.email
        WHEN id.phoneNumber IS NOT NULL THEN id.phoneNumber
        ELSE id.ssn
      END AS deviceId,
      head(labels(id)) AS deviceType,
      size(allAccounts) AS totalAccounts,
      riskyCount AS riskyAccounts
    ORDER BY riskyAccounts DESC, totalAccounts DESC
    LIMIT $limit
    """
    result = tx.run(
        cypher,
        highRiskThreshold=high_risk,
        minRiskyAccounts=min_risky,
        limit=limit,
    )
    return [record.data() for record in result]


def fetch_mule_ring_alerts_r3(tx, min_risky: int, limit: int):
    """
    Xavier data: detect mule rings as mules densely connected to other mules via TRANSACTED_WITH.
    For each Mule, count distinct Mule peers; require count >= min_risky.
    """
    cypher = """
    MATCH (m:Mule)-[:TRANSACTED_WITH]-(peer:Mule)
    WITH m, collect(DISTINCT peer) AS peers, size(collect(DISTINCT peer)) AS ringSize
    WHERE ringSize >= $minRisky
    RETURN
      m.id   AS accountId,
      m.name AS customerName,
      1.0    AS riskScore,
      true   AS isFraud,
      ringSize AS ringSize
    ORDER BY ringSize DESC, accountId
    LIMIT $limit
    """
    result = tx.run(cypher, minRisky=min_risky, limit=limit)
    return [record.data() for record in result]


def fetch_hub_alerts_r7(tx, risk_threshold: float, min_risky: int, limit: int):
    """
    Xavier: risky senders are mules. Count distinct Mule senders to each destination
    (Client or Mule) via PERFORMED->tx->TO edges.
    """
    cypher = """
    MATCH (src:Mule)-[:PERFORMED]->(tx:Transaction)-[:TO]->(dst)
    WHERE dst:Client OR dst:Mule
    WITH dst, collect(DISTINCT src) AS riskySenders, count(DISTINCT src) AS riskyCount, count(DISTINCT tx) AS txCount
    WHERE riskyCount >= $minRiskyAccounts
    RETURN
      dst.id   AS accountId,
      coalesce(dst.name, dst.id) AS customerName,
      1.0    AS riskScore,
      (dst:Mule) AS isFraud,
      riskyCount AS riskySenders,
      txCount AS txCount
    ORDER BY riskyCount DESC, txCount DESC
    LIMIT $limit
    """
    result = tx.run(
        cypher,
        riskThreshold=risk_threshold,
        minRiskyAccounts=min_risky,
        limit=limit,
    )
    return [record.data() for record in result]


def create_app():
    load_dotenv()
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)

    verify_database_connection()

    app.register_blueprint(alerts_bp, url_prefix="/api")
    app.register_blueprint(cases_bp, url_prefix="/api")
    app.register_blueprint(rules_bp, url_prefix="/api")
    app.register_blueprint(neo4j_bp, url_prefix="/api")
    app.register_blueprint(investigator_bp, url_prefix="/api")

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    @app.route("/api/neo-alerts", methods=["GET"])
    def neo4j_account_alerts():
        if not driver:
            return jsonify({"status": "error", "message": "Neo4j driver not configured"}), 500
        with driver.session() as session:
            records = session.execute_read(fetch_account_alerts, 0.8)
        alerts = []
        for idx, rec in enumerate(records, start=1):
            risk = rec.get("riskScore") or 0
            if risk >= 0.95:
                severity = "Critical"
            elif risk >= 0.9:
                severity = "High"
            else:
                severity = "Medium"
            summary = f"{rec.get('customerName')} ({rec.get('accountId')}) risk={risk:.2f}"
            alerts.append(
                {
                    "id": idx,
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "riskScore": risk,
                    "severity": severity,
                    "rule": "High risk score / flagged account",
                    "summary": summary,
                    "status": "Open",
                    "created": datetime.utcnow().isoformat() + "Z",
                }
            )
        return jsonify(alerts)

    @app.route("/api/neo-alerts/r1", methods=["GET"])
    def neo4j_account_alerts_r1():
        if not driver:
            return jsonify({"status": "error", "message": "Neo4j driver not configured"}), 500
        try:
            risk_threshold = float(request.args.get("riskThreshold", 0.8))
        except Exception:
            risk_threshold = 0.8
        try:
            limit = int(request.args.get("limit", 50))
        except Exception:
            limit = 50
        with driver.session() as session:
            records = session.execute_read(fetch_account_alerts_r1, risk_threshold, limit)
        alerts = []
        for idx, rec in enumerate(records, start=1):
            if not is_flagged_record(rec, "ACCOUNT"):
                continue
            risk = rec.get("riskScore") or 0
            if risk >= 0.95:
                severity = "Critical"
            elif risk >= 0.9:
                severity = "High"
            else:
                severity = "Medium"
            summary = f"{rec.get('customerName')} ({rec.get('accountId')}) risk={risk:.2f} is_fraud={rec.get('isFraud')}"
            alerts.append(
                {
                    "id": idx,
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "riskScore": risk,
                    "severity": severity,
                    "rule": "R1 – High risk / flagged account",
                    "summary": summary,
                    "status": "Open",
                    "created": datetime.utcnow().isoformat() + "Z",
                }
            )
        return jsonify(alerts)

    @app.route("/api/neo-alerts/r2", methods=["GET"])
    def neo4j_device_alerts_r2():
        if not driver:
            return jsonify({"status": "error", "message": "Neo4j driver not configured"}), 500
        try:
            high_risk = float(request.args.get("highRiskThreshold", 0.8))
        except Exception:
            high_risk = 0.8
        try:
            min_risky = int(request.args.get("minRiskyAccounts", 2))
        except Exception:
            min_risky = 2
        try:
            limit = int(request.args.get("limit", 20))
        except Exception:
            limit = 20
        with driver.session() as session:
            records = session.execute_read(fetch_device_alerts_r2, high_risk, min_risky, limit)

        alerts = []
        for idx, rec in enumerate(records, start=1):
            risky = rec.get("riskyAccounts") or 0
            total = rec.get("totalAccounts") or 0
            severity = "High" if risky >= 3 else "Medium"
            summary = f"Identifier {rec.get('deviceId')} ({rec.get('deviceType')}) linked to {risky} risky / {total} total accounts"
            alerts.append(
                {
                    "id": idx,
                    "deviceId": rec.get("deviceId"),
                    "deviceType": rec.get("deviceType"),
                    "riskyAccounts": risky,
                    "totalAccounts": total,
                    "severity": severity,
                    "rule": "R2 – Shared risky device",
                    "summary": summary,
                    "status": "Open",
                    "created": datetime.utcnow().isoformat() + "Z",
                }
            )
        return jsonify(alerts)

    @app.route("/api/neo-alerts/r3", methods=["GET"])
    def neo4j_mule_ring_alerts_r3():
        if not driver:
            return jsonify({"status": "error", "message": "Neo4j driver not configured"}), 500
        try:
            min_risky = int(request.args.get("minRiskyAccounts", 3))
        except Exception:
            min_risky = 3
        try:
            limit = int(request.args.get("limit", 20))
        except Exception:
            limit = 20
        with driver.session() as session:
            records = session.execute_read(fetch_mule_ring_alerts_r3, min_risky, limit)

        alerts = []
        for idx, rec in enumerate(records, start=1):
            if not is_flagged_record(rec, "ACCOUNT"):
                continue
            ring_size = rec.get("ringSize") or 0
            risk = rec.get("riskScore") or 0
            severity = "Critical" if ring_size >= 5 else "High"
            summary = f"Account {rec.get('accountId')} in ring of size {ring_size} (risk={risk:.2f})"
            alerts.append(
                {
                    "id": idx,
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "riskScore": risk,
                    "ringSize": ring_size,
                    "severity": severity,
                    "rule": "R3 – Mule ring flow",
                    "summary": summary,
                    "status": "Open",
                    "created": datetime.utcnow().isoformat() + "Z",
                }
            )
        return jsonify(alerts)

    @app.route("/api/neo-alerts/r7", methods=["GET"])
    def neo4j_hub_alerts_r7():
        if not driver:
            return jsonify({"status": "error", "message": "Neo4j driver not configured"}), 500
        try:
            risk_threshold = float(request.args.get("riskThreshold", 0.8))
        except Exception:
            risk_threshold = 0.8
        try:
            min_risky = int(request.args.get("minRiskyAccounts", 3))
        except Exception:
            min_risky = 3
        try:
            limit = int(request.args.get("limit", 20))
        except Exception:
            limit = 20

        with driver.session() as session:
            records = session.execute_read(fetch_hub_alerts_r7, risk_threshold, min_risky, limit)

        alerts = []
        for idx, rec in enumerate(records, start=1):
            if not is_flagged_record(rec, "ACCOUNT"):
                continue
            risky = rec.get("riskySenders") or 0
            tx_count = rec.get("txCount") or 0
            risk = rec.get("riskScore") or 0
            severity = "Critical" if risky >= 5 else "High"
            summary = f"Hub {rec.get('accountId')} receives from {risky} risky senders ({tx_count} tx)"
            alerts.append(
                {
                    "id": idx,
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "riskScore": risk,
                    "riskySenders": risky,
                    "txCount": tx_count,
                    "severity": severity,
                    "rule": "R7 – Risky funnel to hub",
                    "summary": summary,
                    "status": "Open",
                    "created": datetime.utcnow().isoformat() + "Z",
                }
            )
        return jsonify(alerts)

    @app.route("/api/neo-alerts/search", methods=["GET"])
    def neo4j_search_all_rules():
        if not driver:
            return jsonify({"status": "error", "message": "Neo4j driver not configured"}), 500
        try:
            risk_threshold = float(request.args.get("riskThreshold", 0.8))
        except Exception:
            risk_threshold = 0.8
        try:
            high_risk = float(request.args.get("highRiskThreshold", 0.8))
        except Exception:
            high_risk = risk_threshold
        try:
            min_risky = int(request.args.get("minRiskyAccounts", 3))
        except Exception:
            min_risky = 3
        try:
            limit = int(request.args.get("limit", 20))
        except Exception:
            limit = 20
        exclude_flagged = str(request.args.get("excludeFlagged", "false")).lower() == "true"

        alerts = []
        with driver.session() as session:
            r1 = session.execute_read(fetch_account_alerts_r1, risk_threshold, limit)
            r2 = session.execute_read(fetch_device_alerts_r2, high_risk, min_risky, limit)
            r3 = session.execute_read(fetch_mule_ring_alerts_r3, min_risky, limit)
            r7 = session.execute_read(fetch_hub_alerts_r7, risk_threshold, min_risky, limit)

            def is_flagged(rec, anchor_type):
                anchor_id = (rec.get("accountId") or rec.get("deviceId"))
                if not anchor_id:
                    return False
                return is_locally_flagged(anchor_id, anchor_type)

            # R1
            for idx, rec in enumerate(r1, start=1):
                if exclude_flagged and is_flagged(rec, "ACCOUNT"):
                    continue
                risk = rec.get("riskScore") or 0
                if risk >= 0.95:
                    severity = "Critical"
                elif risk >= 0.9:
                    severity = "High"
                else:
                    severity = "Medium"
                summary = f"{rec.get('customerName')} ({rec.get('accountId')}) risk={risk:.2f} is_fraud={rec.get('isFraud')}"
                alerts.append(
                    {
                        "ruleKey": "R1",
                        "id": f"R1-{idx}",
                        "accountId": rec.get("accountId"),
                        "customerName": rec.get("customerName"),
                        "riskScore": risk,
                        "severity": severity,
                        "rule": "R1 – High risk / flagged account",
                        "summary": summary,
                        "status": "Open",
                        "created": datetime.utcnow().isoformat() + "Z",
                    }
                )
            # R2
            for idx, rec in enumerate(r2, start=1):
                risky = rec.get("riskyAccounts") or 0
                total = rec.get("totalAccounts") or 0
                severity = "High" if risky >= 3 else "Medium"
                if exclude_flagged and is_flagged(rec, "DEVICE"):
                    continue
                summary = f"Identifier {rec.get('deviceId')} ({rec.get('deviceType')}) linked to {risky} risky / {total} total accounts"
                alerts.append(
                    {
                        "ruleKey": "R2",
                        "id": f"R2-{idx}",
                        "deviceId": rec.get("deviceId"),
                        "deviceType": rec.get("deviceType"),
                        "riskyAccounts": risky,
                        "totalAccounts": total,
                        "severity": severity,
                        "rule": "R2 – Shared risky device",
                        "summary": summary,
                        "status": "Open",
                        "created": datetime.utcnow().isoformat() + "Z",
                    }
                )
            # R3
            for idx, rec in enumerate(r3, start=1):
                if exclude_flagged and is_flagged(rec, "ACCOUNT"):
                    continue
                ring_size = rec.get("ringSize") or 0
                risk = rec.get("riskScore") or 0
                severity = "Critical" if ring_size >= 5 else "High"
                summary = f"Account {rec.get('accountId')} in ring of size {ring_size} (risk={risk:.2f})"
                alerts.append(
                    {
                        "ruleKey": "R3",
                        "id": f"R3-{idx}",
                        "accountId": rec.get("accountId"),
                        "customerName": rec.get("customerName"),
                        "riskScore": risk,
                        "ringSize": ring_size,
                        "severity": severity,
                        "rule": "R3 – Mule ring flow",
                        "summary": summary,
                        "status": "Open",
                        "created": datetime.utcnow().isoformat() + "Z",
                    }
                )
            # R7
            for idx, rec in enumerate(r7, start=1):
                if exclude_flagged and is_flagged(rec, "ACCOUNT"):
                    continue
                risky = rec.get("riskySenders") or 0
                tx_count = rec.get("txCount") or 0
                risk = rec.get("riskScore") or 0
                severity = "Critical" if risky >= 5 else "High"
                summary = f"Hub {rec.get('accountId')} receives from {risky} risky senders ({tx_count} tx)"
                alerts.append(
                    {
                        "ruleKey": "R7",
                        "id": f"R7-{idx}",
                        "accountId": rec.get("accountId"),
                        "customerName": rec.get("customerName"),
                        "riskScore": risk,
                        "riskySenders": risky,
                        "txCount": tx_count,
                        "severity": severity,
                        "rule": "R7 – Risky funnel to hub",
                        "summary": summary,
                        "status": "Open",
                        "created": datetime.utcnow().isoformat() + "Z",
                    }
                )
        return jsonify(alerts)

    @app.route("/api/db-health", methods=["GET"])
    def db_health():
        try:
            verify_database_connection()
            return jsonify({"status": "ok"})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500

    with app.app_context():
        init_db()

    return app


def init_db():
    Base.metadata.create_all(bind=engine)
    seed_data()


def verify_database_connection():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def seed_data():
    session = get_session()
    try:
        existing_rules = session.execute(select(RuleDefinition)).scalars().all()
        if not existing_rules:
            rules = [
                RuleDefinition(
                    name="Mule Ring Detection",
                    description="Detects accounts connected via shared devices and rapid transfers.",
                    cypher_query="MATCH (a:Account)-[:USES]->(d:Device)<-[:USES]-(m:Account) RETURN a, d, collect(m)",
                    severity="CRITICAL",
                ),
                RuleDefinition(
                    name="Identity Fraud Detection",
                    description="Flags identity mismatches across devices and KYC data.",
                    cypher_query="MATCH (a:Account)-[:USES]->(d:Device)<-[:USES]-(b:Account) WHERE a.kyc_id <> b.kyc_id RETURN a, b, d",
                    severity="HIGH",
                ),
            ]
            session.add_all(rules)

        existing_accounts = session.execute(select(Account)).scalars().all()
        if not existing_accounts:
            accounts = [
                Account(account_number="GCASH-100123", customer_name="Juan Dela Cruz", risk_score=0.85),
                Account(account_number="GCASH-200001", customer_name="Mule Account 1", risk_score=0.9),
                Account(account_number="GCASH-200002", customer_name="Mule Account 2", risk_score=0.88),
                Account(account_number="GCASH-200003", customer_name="Mule Account 3", risk_score=0.86),
                Account(account_number="GCASH-300001", customer_name="Maria Santos", risk_score=0.7),
                Account(account_number="GCASH-300002", customer_name="Maria Santos", risk_score=0.65),
            ]
            session.add_all(accounts)

        existing_devices = session.execute(select(Device)).scalars().all()
        if not existing_devices:
            devices = [
                Device(device_id="DEV-12345", device_type="Android"),
                Device(device_id="DEV-54321", device_type="iOS"),
            ]
            session.add_all(devices)

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
