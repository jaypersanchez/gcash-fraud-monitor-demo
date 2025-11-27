import os
import sys
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify
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
from backend.routes.alerts import alerts_bp
from backend.routes.cases import cases_bp
from backend.routes.rules import rules_bp
from backend.routes.neo4j import neo4j_bp

# Neo4j driver (global)
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
driver = None
if all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def fetch_account_alerts(tx, min_risk: float):
    cypher = """
    MATCH (a:Account)
    WHERE a.is_fraud = true
       OR a.is_fraud = "True"
       OR a.risk_score >= $minRisk
    RETURN
      a.account_number AS accountId,
      a.customer_name  AS customerName,
      a.risk_score     AS riskScore,
      a.is_fraud       AS isFraud
    ORDER BY riskScore DESC
    LIMIT 100
    """
    result = tx.run(cypher, minRisk=min_risk)
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
