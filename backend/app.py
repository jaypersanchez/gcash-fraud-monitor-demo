import os
import sys
import uuid
import tempfile
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from sqlalchemy import select, text
from neo4j import GraphDatabase
from neo4j.graph import Path as NeoPath
import requests

# Ensure project root is on sys.path when running directly from backend/
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import Config
from backend.db.session import engine, get_session
from backend.models import Base, RuleDefinition, Account, Device, Alert
from backend.models.investigator_action import InvestigatorAction
from backend.routes.alerts import alerts_bp
from backend.routes.cases import cases_bp
from backend.routes.rules import rules_bp
from backend.routes.neo4j import neo4j_bp
from backend.routes.investigator import investigator_bp
from backend.routes.afasa import afasa_bp

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


def _detect_flag(obj: dict, labels=None) -> bool:
    labels = labels or []
    if "Mule" in labels:
        return True
    if obj.get("fraud_group") is not None:
        return True
    if obj.get("flagged"):
        return True
    val = obj.get("is_fraud")
    if isinstance(val, str):
        val = val.lower() in {"true", "1", "yes"}
    return bool(val)


def _graph_for_account(account_id: str):
    cypher = """
    MATCH (a)
    WHERE (a:Account AND a.account_number = $accountId)
       OR (a:Mule AND a.id = $accountId)
       OR (a:Client AND a.id = $accountId)
    OPTIONAL MATCH (a)-[:HAS_EMAIL|HAS_PHONE|HAS_SSN]->(id)<-[:HAS_EMAIL|HAS_PHONE|HAS_SSN]-(peer)
    OPTIONAL MATCH (a)-[:PERFORMED]->(txOut:Transaction)-[:TO]->(dst)
    OPTIONAL MATCH (src)-[:PERFORMED]->(txIn:Transaction)-[:TO]->(a)
    RETURN a, labels(a) AS a_labels,
           collect(DISTINCT id) AS identifiers,
           collect(DISTINCT {idNode:id, peer:peer, peerLabels:labels(peer)}) AS idPeers,
           collect(DISTINCT {tx:txOut, other:dst, otherLabels:labels(dst), direction:'OUT'}) AS outbound,
           collect(DISTINCT {tx:txIn, other:src, otherLabels:labels(src), direction:'IN'}) AS inbound
    """
    nodes = {}
    edges = []

    def add_node(key, label, ntype, extra=None):
        if key in nodes:
            return
        node = {"id": key, "label": label, "type": ntype}
        if extra:
            node.update(extra)
        nodes[key] = node

    with driver.session() as session:
        record = session.run(cypher, accountId=account_id).single()
        if not record:
            return {"nodes": [], "edges": []}
        a = record["a"]
        anchor_id = a.get("account_number") or a.get("id")
        anchor_label = a.get("customer_name") or a.get("name") or anchor_id
        flagged_anchor = _detect_flag(a, record.get("a_labels") or [])
        add_node(anchor_id, anchor_label, "Account", {"customerName": anchor_label, "isSubject": True, "isFlagged": flagged_anchor})

        identifiers = record.get("identifiers") or []
        for id_node in identifiers:
            device_id = id_node.get("device_id") or id_node.get("email") or id_node.get("phoneNumber") or id_node.get("ssn")
            if not device_id:
                continue
            dev_type = "Device"
            if "email" in id_node:
                dev_type = "Email"
            elif "phoneNumber" in id_node:
                dev_type = "Phone"
            elif "ssn" in id_node:
                dev_type = "SSN"
            flagged_id = _detect_flag(id_node)
            add_node(device_id, device_id, "Device", {"deviceType": dev_type, "isFlagged": flagged_id})
            edges.append({"source": anchor_id, "target": device_id, "type": "HAS_IDENTIFIER"})

        id_peers = record.get("idPeers") or []
        for entry in id_peers:
            id_node = entry.get("idNode") or {}
            peer = entry.get("peer") or {}
            peer_labels = entry.get("peerLabels") or []
            device_id = id_node.get("device_id") or id_node.get("email") or id_node.get("phoneNumber") or id_node.get("ssn")
            peer_id = peer.get("account_number") or peer.get("id")
            if not device_id or not peer_id:
                continue
            peer_label = peer.get("customer_name") or peer.get("name") or peer_id
            flagged_peer = _detect_flag(peer, peer_labels)
            add_node(peer_id, peer_label, "Account", {"customerName": peer_label, "isFlagged": flagged_peer})
            add_node(device_id, device_id, "Device", {"deviceType": "Identifier", "isFlagged": _detect_flag(id_node)})
            edges.append({"source": peer_id, "target": device_id, "type": "HAS_IDENTIFIER"})

        def handle_tx(items):
            for item in items or []:
                tx = item.get("tx")
                other = item.get("other")
                other_labels = item.get("otherLabels") or []
                direction = item.get("direction")
                if not tx or not other:
                    continue
                tx_ref = tx.get("tx_ref") or tx.get("id")
                add_node(tx_ref, tx_ref, "Transaction", {"amount": tx.get("amount"), "tags": tx.get("tags")})
                other_id = other.get("account_number") or other.get("id")
                other_label = other.get("customer_name") or other.get("name") or other_id
                flagged_other = _detect_flag(other, other_labels)
                add_node(other_id, other_label, "Account", {"customerName": other_label, "isFlagged": flagged_other})
                if direction == "OUT":
                    edges.append({"source": anchor_id, "target": tx_ref, "type": "PERFORMS"})
                    edges.append({"source": tx_ref, "target": other_id, "type": "TO"})
                else:
                    edges.append({"source": other_id, "target": tx_ref, "type": "PERFORMS"})
                    edges.append({"source": tx_ref, "target": anchor_id, "type": "TO"})

        handle_tx(record.get("outbound"))
        handle_tx(record.get("inbound"))

    return {"nodes": list(nodes.values()), "edges": edges}


def _graph_for_identifier(identifier: str):
    cypher = """
    MATCH (id)
    WHERE (id:Email AND id.email = $identifier)
       OR (id:Phone AND id.phoneNumber = $identifier)
       OR (id:SSN AND id.ssn = $identifier)
    OPTIONAL MATCH (id)<-[:HAS_EMAIL|HAS_PHONE|HAS_SSN]-(acc)
    OPTIONAL MATCH (acc)-[:PERFORMED]->(txOut:Transaction)-[:TO]->(dst)
    OPTIONAL MATCH (src)-[:PERFORMED]->(txIn:Transaction)-[:TO]->(acc)
    RETURN id,
           collect(DISTINCT {acc: acc, accLabels: labels(acc)}) AS accounts,
           collect(DISTINCT {tx: txOut, other: dst, otherLabels: labels(dst), direction: 'OUT', acc: acc, accLabels: labels(acc)}) AS outbound,
           collect(DISTINCT {tx: txIn, other: src, otherLabels: labels(src), direction: 'IN', acc: acc, accLabels: labels(acc)}) AS inbound
    """
    nodes = {}
    edges = []

    def add_node(key, label, ntype, extra=None):
        if key in nodes:
            return
        node = {"id": key, "label": label, "type": ntype}
        if extra:
            node.update(extra)
        nodes[key] = node

    with driver.session() as session:
        record = session.run(cypher, identifier=identifier).single()
        if not record:
            return {"nodes": [], "edges": []}

        id_node = record["id"]
        device_id_val = id_node.get("device_id") or id_node.get("email") or id_node.get("phoneNumber") or id_node.get("ssn")
        device_type = "Device"
        if "email" in id_node:
            device_type = "Email"
        elif "phoneNumber" in id_node:
            device_type = "Phone"
        elif "ssn" in id_node:
            device_type = "SSN"
        flagged_id = _detect_flag(id_node)
        add_node(device_id_val, device_id_val, "Device", {"deviceType": device_type, "isSubject": True, "isFlagged": flagged_id})

        for acc_entry in record.get("accounts") or []:
            acc = acc_entry.get("acc") or {}
            acc_labels = acc_entry.get("accLabels") or []
            acc_id = acc.get("account_number") or acc.get("id")
            acc_label = acc.get("customer_name") or acc.get("name") or acc_id
            flagged_acc = _detect_flag(acc, acc_labels)
            add_node(acc_id, acc_label, "Account", {"customerName": acc_label, "isFlagged": flagged_acc})
            edges.append({"source": acc_id, "target": device_id_val, "type": "HAS_IDENTIFIER"})

        def handle_tx(items):
            for item in items or []:
                tx = item.get("tx")
                other = item.get("other")
                acc = item.get("acc")
                acc_labels = item.get("accLabels") or []
                direction = item.get("direction")
                if not tx or not other or not acc:
                    continue
                tx_ref = tx.get("tx_ref") or tx.get("id")
                add_node(tx_ref, tx_ref, "Transaction", {"amount": tx.get("amount"), "tags": tx.get("tags")})
                other_id = other.get("account_number") or other.get("id")
                other_label = other.get("customer_name") or other.get("name") or other_id
                acc_id = acc.get("account_number") or acc.get("id")
                acc_label = acc.get("customer_name") or acc.get("name") or acc_id
                flagged_acc = _detect_flag(acc, acc_labels)
                add_node(other_id, other_label, "Account", {"customerName": other_label})
                add_node(acc_id, acc_label, "Account", {"customerName": acc_label, "isFlagged": flagged_acc})
                if direction == "OUT":
                    edges.append({"source": acc_id, "target": tx_ref, "type": "PERFORMS"})
                    edges.append({"source": tx_ref, "target": other_id, "type": "TO"})
                else:
                    edges.append({"source": other_id, "target": tx_ref, "type": "PERFORMS"})
                    edges.append({"source": tx_ref, "target": acc_id, "type": "TO"})

        handle_tx(record.get("outbound"))
        handle_tx(record.get("inbound"))

    return {"nodes": list(nodes.values()), "edges": edges}


def _render_dot_png(nodes, edges):
    """Render a simple graph PNG using graphviz dot if available."""
    dot_lines = ["digraph G {", 'rankdir="LR";', 'node [style=filled,fontname="Arial"];']
    for n in nodes:
        color = "#6ba7ff" if n.get("type") == "Account" else "#6adedc" if n.get("type") == "Device" else "#ffd166"
        if n.get("isFlagged"):
            color = "#e63946"
        if n.get("isSubject"):
            color = "#ff8c42"
        shape = "ellipse"
        if n.get("type") == "Device":
            shape = "diamond"
        if n.get("type") == "Transaction":
            shape = "box"
        label = n.get("label") or n.get("id")
        dot_lines.append(f'"{n["id"]}" [label="{label}", color="#0c1a36", fillcolor="{color}", shape="{shape}"];')
    for e in edges:
        lbl = e.get("type") or ""
        dot_lines.append(f'"{e["source"]}" -> "{e["target"]}" [label="{lbl}", color="#a5b4d0"];')
    dot_lines.append("}")
    dot_src = "\n".join(dot_lines)
    tmpdir = Path(tempfile.gettempdir()) / "gcash_graphs"
    tmpdir.mkdir(parents=True, exist_ok=True)
    png_path = tmpdir / f"{uuid.uuid4().hex}.png"
    try:
        proc = subprocess.run(["dot", "-Tpng"], input=dot_src.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        with open(png_path, "wb") as f:
            f.write(proc.stdout)
        return str(png_path)
    except Exception as exc:
        print(f"dot render failed: {exc}")
        return None


def is_flagged_record(rec: dict, anchor_type: str) -> bool:
    anchor_id = rec.get("accountId") or rec.get("deviceId")
    if not anchor_id:
        return False
    if str(rec.get("isFraud")).lower() == "true":
        return True
    return is_locally_flagged(anchor_id, anchor_type)


def _node_prop(node, keys):
    """Safe helper to pull the first available property from a Neo4j node."""
    if not node:
        return None
    for k in keys:
        try:
            if k in node:
                return node[k]
        except Exception:
            continue
    return None


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


def _path_stats(path: NeoPath):
    rels = list(path.relationships)
    steps = len(rels)
    amounts = []
    times = []
    for r in rels:
        try:
            if "amount" in r:
                amounts.append(r["amount"])
        except Exception:
            pass
        try:
            if "globalStep" in r:
                times.append(r["globalStep"])
        except Exception:
            pass
    return {
        "steps": steps,
        "max_amount": max(amounts) if amounts else 0,
        "min_amount": min(amounts) if amounts else 0,
        "time_span": (max(times) - min(times)) if len(times) >= 2 else 0,
    }


def fetch_progressive_chain_r8(tx, name: str, duration: int, amount: float, min_hops: int, max_hops: int, limit: int):
    """
    Progressive multi-hop chain within a time window where amounts start high and decrease.
    Based on Neo4j-provided pattern (10–20 hops, window duration, min amount).
    """
    min_hops = max(1, min_hops)
    max_hops = max(min_hops, min(max_hops, 15))
    name_filter = " {name: $name}" if name else ""
    cypher = f"""
    MATCH p=(c1:Client{name_filter})
    (
      (:Client)-[t1:TRANSACTED_WITH]->(:Client)-[t2:TRANSACTED_WITH]->(:Client)
      WHERE t1.globalStep + $duration > t2.globalStep > t1.globalStep
        AND t2.amount < t1.amount
        AND t1.amount > $amount
    ){{{min_hops},{max_hops}}}(c2:Client)
    RETURN p
    LIMIT $limit
    """
    results = []
    for record in tx.run(cypher, name=name, duration=duration, amount=amount, limit=limit):
        path = record["p"]
        stats = _path_stats(path)
        start = path.start_node
        end = path.end_node
        account_id = _node_prop(start, ["id", "account_number"]) or name
        customer_name = _node_prop(start, ["name", "customer_name"]) or name
        severity = "Critical" if stats["steps"] >= 15 or stats["max_amount"] >= amount * 2 else "High"
        summary = (
            f"{customer_name} progressive chain {stats['steps']} hops "
            f"(max {stats['max_amount']:,} in window {duration})"
        )
        results.append(
            {
                "accountId": account_id,
                "customerName": customer_name,
                "pathLength": stats["steps"],
                "maxAmount": stats["max_amount"],
                "timeSpan": stats["time_span"],
                "isFraud": False,
                "severity": severity,
                "summary": summary,
            }
        )
    return results


def fetch_cycle_r9(tx, name: str, min_amount: float, min_hops: int, max_hops: int, limit: int):
    """
    Long high-value cycle (returns to same client) with min amount on each hop.
    """
    min_hops = max(1, min_hops)
    max_hops = max(min_hops, min(max_hops, 15))
    name_filter = " {name: $name}" if name else ""
    cypher = f"""
    MATCH p=(c:Client{name_filter})-[r:TRANSACTED_WITH WHERE r.amount > $minAmount]->{{{min_hops},{max_hops}}}(c)
    RETURN p
    LIMIT $limit
    """
    results = []
    for record in tx.run(cypher, name=name, minAmount=min_amount, limit=limit):
        path = record["p"]
        stats = _path_stats(path)
        start = path.start_node
        account_id = _node_prop(start, ["id", "account_number"]) or name
        customer_name = _node_prop(start, ["name", "customer_name"]) or name
        severity = "Critical" if stats["steps"] >= 18 or stats["max_amount"] >= min_amount * 1.2 else "High"
        summary = f"{customer_name} cycle {stats['steps']} hops (min hop amount > {min_amount:,})"
        results.append(
            {
                "accountId": account_id,
                "customerName": customer_name,
                "pathLength": stats["steps"],
                "maxAmount": stats["max_amount"],
                "timeSpan": stats["time_span"],
                "isFraud": False,
                "severity": severity,
                "summary": summary,
            }
        )
    return results


def fetch_progressive_high_value_r10(tx, name: str, min_amount: float, min_hops: int, max_hops: int, limit: int):
    """
    Progressive time-ordered high-value chains (r2 after r1, both above threshold).
    """
    min_hops = max(1, min_hops)
    max_hops = max(min_hops, min(max_hops, 15))
    name_filter = " {name: $name}" if name else ""
    cypher = f"""
    MATCH p=(c:Client{name_filter})
    (
      (:Client)-[r1:TRANSACTED_WITH]->(:Client)-[r2:TRANSACTED_WITH]->(:Client)
      WHERE r2.globalStep > r1.globalStep
        AND r1.amount > $minAmount
        AND r2.amount > $minAmount
    ){{{min_hops},{max_hops}}}(c)
    RETURN p
    LIMIT $limit
    """
    results = []
    for record in tx.run(cypher, name=name, minAmount=min_amount, limit=limit):
        path = record["p"]
        stats = _path_stats(path)
        start = path.start_node
        account_id = _node_prop(start, ["id", "account_number"]) or name
        customer_name = _node_prop(start, ["name", "customer_name"]) or name
        severity = "Critical" if stats["steps"] >= 8 or stats["max_amount"] >= min_amount * 1.5 else "High"
        summary = f"{customer_name} time-ordered chain {stats['steps']} hops (min amount > {min_amount:,})"
        results.append(
            {
                "accountId": account_id,
                "customerName": customer_name,
                "pathLength": stats["steps"],
                "maxAmount": stats["max_amount"],
                "timeSpan": stats["time_span"],
                "isFraud": False,
                "severity": severity,
                "summary": summary,
            }
        )
    return results


def create_app():
    load_dotenv()
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)

    @app.after_request
    def add_cors_headers(response):
        # Ensure all endpoints (including new ones) emit permissive CORS for local demos.
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    verify_database_connection()

    app.register_blueprint(alerts_bp, url_prefix="/api")
    app.register_blueprint(cases_bp, url_prefix="/api")
    app.register_blueprint(rules_bp, url_prefix="/api")
    app.register_blueprint(neo4j_bp, url_prefix="/api")
    app.register_blueprint(investigator_bp, url_prefix="/api")
    app.register_blueprint(afasa_bp, url_prefix="/api")

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

    @app.route("/api/neo-alerts/r8", methods=["GET"])
    def neo4j_progressive_chains_r8():
        if not driver:
            return jsonify({"status": "error", "message": "Neo4j driver not configured"}), 500
        name = request.args.get("name", "Aubree David")
        try:
            duration = int(request.args.get("duration", 4000))
        except Exception:
            duration = 4000
        try:
            amount = float(request.args.get("amount", 50000))
        except Exception:
            amount = 50000.0
        try:
            min_hops = int(request.args.get("minHops", 5))
        except Exception:
            min_hops = 5
        try:
            max_hops = int(request.args.get("maxHops", 10))
        except Exception:
            max_hops = 10
        try:
            limit = int(request.args.get("limit", 5))
        except Exception:
            limit = 5

        with driver.session() as session:
            records = session.execute_read(fetch_progressive_chain_r8, name, duration, amount, min_hops, max_hops, limit)

        alerts = []
        for idx, rec in enumerate(records, start=1):
            severity = rec.get("severity") or "High"
            summary = rec.get("summary") or "Progressive chain detected"
            alerts.append(
                {
                    "id": idx,
                    "ruleKey": "R8",
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "severity": severity,
                    "rule": "R8 – Progressive time-window chain",
                    "summary": summary,
                    "pathLength": rec.get("pathLength"),
                    "maxAmount": rec.get("maxAmount"),
                    "status": "Open",
                    "created": datetime.utcnow().isoformat() + "Z",
                }
            )
        return jsonify(alerts)

    @app.route("/api/neo-alerts/r9", methods=["GET"])
    def neo4j_cycle_r9():
        if not driver:
            return jsonify({"status": "error", "message": "Neo4j driver not configured"}), 500
        name = request.args.get("name", "Aubree David")
        try:
            min_amount = float(request.args.get("minAmount", 1200000))
        except Exception:
            min_amount = 1200000.0
        try:
            min_hops = int(request.args.get("minHops", 10))
        except Exception:
            min_hops = 10
        try:
            max_hops = int(request.args.get("maxHops", 12))
        except Exception:
            max_hops = 12
        try:
            limit = int(request.args.get("limit", 5))
        except Exception:
            limit = 5

        with driver.session() as session:
            records = session.execute_read(fetch_cycle_r9, name, min_amount, min_hops, max_hops, limit)

        alerts = []
        for idx, rec in enumerate(records, start=1):
            severity = rec.get("severity") or "High"
            summary = rec.get("summary") or "Cycle detected"
            alerts.append(
                {
                    "id": idx,
                    "ruleKey": "R9",
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "severity": severity,
                    "rule": "R9 – High-value multi-hop cycle",
                    "summary": summary,
                    "pathLength": rec.get("pathLength"),
                    "maxAmount": rec.get("maxAmount"),
                    "status": "Open",
                    "created": datetime.utcnow().isoformat() + "Z",
                }
            )
        return jsonify(alerts)

    @app.route("/api/neo-alerts/r10", methods=["GET"])
    def neo4j_progressive_high_value_r10():
        if not driver:
            return jsonify({"status": "error", "message": "Neo4j driver not configured"}), 500
        name = request.args.get("name", "Aubree David")
        try:
            min_amount = float(request.args.get("minAmount", 800000))
        except Exception:
            min_amount = 800000.0
        try:
            min_hops = int(request.args.get("minHops", 3))
        except Exception:
            min_hops = 3
        try:
            max_hops = int(request.args.get("maxHops", 8))
        except Exception:
            max_hops = 8
        try:
            limit = int(request.args.get("limit", 5))
        except Exception:
            limit = 5

        with driver.session() as session:
            records = session.execute_read(fetch_progressive_high_value_r10, name, min_amount, min_hops, max_hops, limit)

        alerts = []
        for idx, rec in enumerate(records, start=1):
            severity = rec.get("severity") or "High"
            summary = rec.get("summary") or "Progressive high-value chain"
            alerts.append(
                {
                    "id": idx,
                    "ruleKey": "R10",
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "severity": severity,
                    "rule": "R10 – Time-ordered high-value chain",
                    "summary": summary,
                    "pathLength": rec.get("pathLength"),
                    "maxAmount": rec.get("maxAmount"),
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
            risk_threshold = float(request.args.get("riskThreshold", 0.1))
        except Exception:
            risk_threshold = 0.1
        try:
            high_risk = float(request.args.get("highRiskThreshold", 0.1))
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
        # Search & Destroy runs all R rules by default; exclude flagged to focus on unflagged suspects
        exclude_flagged = True
        include_temporal = True
        name_param = request.args.get("name", "Aubree David")
        try:
            temporal_duration = int(request.args.get("duration", 6500))
        except Exception:
            temporal_duration = 6500
        try:
            temporal_amount = float(request.args.get("amount", 50000))
        except Exception:
            temporal_amount = 50000.0
        try:
            temporal_min_amount = float(request.args.get("minAmount", 1200000))
        except Exception:
            temporal_min_amount = 1200000.0

        alerts = []
        with driver.session() as session:
            r1 = session.execute_read(fetch_account_alerts_r1, risk_threshold, limit)
            r2 = session.execute_read(fetch_device_alerts_r2, high_risk, min_risky, limit)
            r3 = session.execute_read(fetch_mule_ring_alerts_r3, min_risky, limit)
            r7 = session.execute_read(fetch_hub_alerts_r7, risk_threshold, min_risky, limit)
            r8 = []
            r9 = []
            r10 = []
            if include_temporal:
                r8 = session.execute_read(fetch_progressive_chain_r8, name_param, temporal_duration, temporal_amount, 5, 10, min(5, limit))
                r9 = session.execute_read(fetch_cycle_r9, name_param, temporal_min_amount, 10, 12, min(5, limit))
                r10 = session.execute_read(fetch_progressive_high_value_r10, name_param, temporal_min_amount, 3, 8, min(5, limit))

        def is_flagged(rec, anchor_type):
            anchor_id = (rec.get("accountId") or rec.get("deviceId"))
            if not anchor_id:
                return False
            # Treat explicit Neo4j flagged flag and local investigator flags as flagged.
            # Do NOT auto-exclude isFraud so Search & Destroy still surfaces seeded demo cases.
            if rec.get("flagged") is True:
                return True
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

        # R8
        for idx, rec in enumerate(r8, start=1):
            severity = rec.get("severity") or "High"
            summary = rec.get("summary") or "Progressive chain detected"
            alerts.append(
                {
                    "ruleKey": "R8",
                    "id": f"R8-{idx}",
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "severity": severity,
                    "rule": "R8 – Progressive time-window chain",
                    "summary": summary,
                    "pathLength": rec.get("pathLength"),
                    "maxAmount": rec.get("maxAmount"),
                    "status": "Open",
                    "created": datetime.utcnow().isoformat() + "Z",
                }
            )

        # R9
        for idx, rec in enumerate(r9, start=1):
            severity = rec.get("severity") or "High"
            summary = rec.get("summary") or "Cycle detected"
            alerts.append(
                {
                    "ruleKey": "R9",
                    "id": f"R9-{idx}",
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "severity": severity,
                    "rule": "R9 – High-value multi-hop cycle",
                    "summary": summary,
                    "pathLength": rec.get("pathLength"),
                    "maxAmount": rec.get("maxAmount"),
                    "status": "Open",
                    "created": datetime.utcnow().isoformat() + "Z",
                }
            )

        # R10
        for idx, rec in enumerate(r10, start=1):
            severity = rec.get("severity") or "High"
            summary = rec.get("summary") or "Progressive high-value chain"
            alerts.append(
                {
                    "ruleKey": "R10",
                    "id": f"R10-{idx}",
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "severity": severity,
                    "rule": "R10 – Time-ordered high-value chain",
                    "summary": summary,
                    "pathLength": rec.get("pathLength"),
                    "maxAmount": rec.get("maxAmount"),
                    "status": "Open",
                    "created": datetime.utcnow().isoformat() + "Z",
                }
            )
        return jsonify(alerts)

    @app.route("/api/neo4j/resolve", methods=["GET"])
    def neo4j_resolve_identifier():
        """
        Fuzzy resolve a free-text query to possible anchors (account/device/identifier).
        Returns a list of matches so the UI can let the user pick.
        """
        if not driver:
            return jsonify({"status": "error", "message": "Neo4j driver not configured"}), 500
        q = (request.args.get("q") or "").strip()
        if not q:
            return jsonify([])
        q_lower = q.lower()
        results = []
        cypher = """
        MATCH (n)
        WHERE (n.accountId IS NOT NULL AND toLower(n.accountId) CONTAINS $qLower)
           OR (n.deviceId IS NOT NULL AND toLower(n.deviceId) CONTAINS $qLower)
           OR (n.customerName IS NOT NULL AND toLower(n.customerName) CONTAINS $qLower)
           OR (n.name IS NOT NULL AND toLower(n.name) CONTAINS $qLower)
           OR (n.email IS NOT NULL AND toLower(n.email) CONTAINS $qLower)
           OR (n.phoneNumber IS NOT NULL AND toLower(n.phoneNumber) CONTAINS $qLower)
           OR (n.ssn IS NOT NULL AND toLower(n.ssn) CONTAINS $qLower)
        WITH n, labels(n) AS lbls
        RETURN n, lbls
        LIMIT 15
        """
        with driver.session() as session:
            records = session.run(cypher, qLower=q_lower)
            for rec in records:
                node = rec["n"]
                lbls = rec["lbls"]
                raw_props = dict(node)
                props = {}
                for k, v in raw_props.items():
                    try:
                        jsonify(v)
                        props[k] = v
                    except Exception:
                        if hasattr(v, "isoformat"):
                            props[k] = v.isoformat()
                        else:
                            props[k] = str(v)
                label = lbls[0] if lbls else "Node"
                anchor = props.get("accountId") or props.get("deviceId") or props.get("id") or props.get("name") or props.get("ssn") or props.get("phoneNumber") or props.get("email")
                display = props.get("customerName") or props.get("name") or props.get("email") or props.get("ssn") or props.get("phoneNumber") or anchor
                results.append(
                    {
                        "label": label,
                        "anchorId": anchor,
                        "display": display,
                        "props": props,
                    }
                )
        return jsonify(results)

    def run_ai_assessment(rule_key: str, anchor: str):
        graph = _graph_for_identifier(anchor) if rule_key == "R2" else _graph_for_account(anchor)
        png_path = _render_dot_png(graph["nodes"], graph["edges"])

        openai_key = os.getenv("OPENAI_API_KEY")
        assessment = "OpenAI key not configured; no assessment generated."
        if openai_key:
            try:
                prompt = (
                    f"Assess this fraud case. Rule={rule_key}, Anchor={anchor}. "
                    f"Nodes: {len(graph['nodes'])}, Edges: {len(graph['edges'])}. "
                    "Flagged nodes may indicate known fraud. Provide a concise risk assessment and next action."
                )
                resp = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o",
                        "messages": [
                            {"role": "system", "content": "You are a fraud analyst. Be concise."},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 180,
                    },
                    timeout=15,
                )
                print(f"[AI-ASSESS] status={resp.status_code} body={resp.text[:500]}")
                if resp.ok:
                    data = resp.json()
                    assessment = data["choices"][0]["message"]["content"]
                else:
                    assessment = f"OpenAI error: {resp.text}"
            except Exception as exc:
                assessment = f"OpenAI call failed: {exc}"

        return {
            "status": "ok",
            "assessment": assessment,
            "image_path": png_path,
            "ruleKey": rule_key,
            "anchor": anchor,
            "graph": graph,
        }

    def compute_ai_top(risk_threshold=0.8, high_risk=None, min_risky=3, limit=5, exclude_flagged=True):
        if not driver:
            raise RuntimeError("Neo4j driver not configured")
        high_risk = high_risk if high_risk is not None else risk_threshold

        alerts = []
        with driver.session() as session:
            r1 = session.execute_read(fetch_account_alerts_r1, risk_threshold, limit)
            r2 = session.execute_read(fetch_device_alerts_r2, high_risk, min_risky, limit)
            r3 = session.execute_read(fetch_mule_ring_alerts_r3, min_risky, limit)
            r7 = session.execute_read(fetch_hub_alerts_r7, risk_threshold, min_risky, limit)

        def severity_rank(sev: str) -> int:
            order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
            return order.get(sev, 3)

        for idx, rec in enumerate(r1, start=1):
            if exclude_flagged and is_flagged_record(rec, "ACCOUNT"):
                continue
            risk = rec.get("riskScore") or 0
            severity = "Critical" if risk >= 0.95 else "High" if risk >= 0.9 else "Medium"
            alerts.append(
                {
                    "ruleKey": "R1",
                    "id": f"R1-{idx}",
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "severity": severity,
                    "summary": f"{rec.get('customerName')} ({rec.get('accountId')}) risk={risk:.2f}",
                }
            )

        for idx, rec in enumerate(r2, start=1):
            if exclude_flagged and is_flagged_record(rec, "DEVICE"):
                continue
            risky = rec.get("riskyAccounts") or 0
            total = rec.get("totalAccounts") or 0
            severity = "High" if risky >= 3 else "Medium"
            alerts.append(
                {
                    "ruleKey": "R2",
                    "id": f"R2-{idx}",
                    "deviceId": rec.get("deviceId"),
                    "deviceType": rec.get("deviceType"),
                    "severity": severity,
                    "summary": f"{rec.get('deviceId')} linked to {risky} risky / {total} total",
                }
            )

        for idx, rec in enumerate(r3, start=1):
            if exclude_flagged and is_flagged_record(rec, "ACCOUNT"):
                continue
            ring_size = rec.get("ringSize") or 0
            risk = rec.get("riskScore") or 0
            severity = "Critical" if ring_size >= 5 else "High"
            alerts.append(
                {
                    "ruleKey": "R3",
                    "id": f"R3-{idx}",
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "severity": severity,
                    "summary": f"{rec.get('accountId')} in ring size {ring_size} (risk={risk:.2f})",
                }
            )

        for idx, rec in enumerate(r7, start=1):
            if exclude_flagged and is_flagged_record(rec, "ACCOUNT"):
                continue
            risky = rec.get("riskySenders") or 0
            tx_count = rec.get("txCount") or 0
            severity = "Critical" if risky >= 5 else "High"
            alerts.append(
                {
                    "ruleKey": "R7",
                    "id": f"R7-{idx}",
                    "accountId": rec.get("accountId"),
                    "customerName": rec.get("customerName"),
                    "severity": severity,
                    "summary": f"{rec.get('accountId')} receives from {risky} risky senders ({tx_count} tx)",
                }
            )

        # Include FAF alerts from persisted Alert table (rule_key like FAF-%)
        session_db = get_session()
        try:
            faf_results = (
                session_db.query(Alert, RuleDefinition, Account)
                .join(RuleDefinition, Alert.rule_id == RuleDefinition.id)
                .join(Account, Alert.subject_account_id == Account.id)
                .filter(RuleDefinition.name.like("FAF-%"))
                .order_by(Alert.created_at.desc())
                .limit(limit * 2)
                .all()
            )
            for alert_obj, rule_def, acct in faf_results:
                rec = {
                    "ruleKey": rule_def.name,
                    "id": f"{rule_def.name}-{alert_obj.id}",
                    "accountId": acct.account_number,
                    "customerName": acct.customer_name,
                    "severity": (alert_obj.severity or "HIGH").title(),
                    "summary": alert_obj.summary,
                }
                if exclude_flagged and is_flagged_record(rec, "ACCOUNT"):
                    continue
                alerts.append(rec)
        finally:
            session_db.close()

        alerts_sorted = sorted(alerts, key=lambda a: severity_rank(a.get("severity")))
        return alerts_sorted[:limit]

    @app.route("/api/ai-agent/assess", methods=["POST"])
    def ai_agent_assess():
        payload = request.get_json(force=True) or {}
        rule_key = payload.get("ruleKey") or payload.get("rule") or "R1"
        anchor = payload.get("anchor") or payload.get("accountId") or payload.get("deviceId")
        if not anchor:
            return jsonify({"status": "error", "message": "Missing anchor"}), 400
        result = run_ai_assessment(rule_key, anchor)
        return jsonify(result)

    @app.route("/api/ai-agent/top", methods=["GET"])
    def ai_agent_top():
        """
        Background agent helper: list top unflagged suspects across R1/R2/R3/R7.
        """
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
            limit = int(request.args.get("limit", 5))
        except Exception:
            limit = 5

        try:
            alerts = compute_ai_top(
                risk_threshold=risk_threshold,
                high_risk=high_risk,
                min_risky=min_risky,
                limit=limit,
                exclude_flagged=True,
            )
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc)}), 500
        return jsonify(alerts)

    def _telegram_send_message(chat_id: str, text: str, reply_markup=None):
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=15
        )
        resp.raise_for_status()
        return resp.json()

    def _telegram_send_photo(chat_id: str, caption: str, photo_path: str):
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
        with open(photo_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": f},
                timeout=20,
            )
        resp.raise_for_status()
        return resp.json()

    def _telegram_answer_callback(callback_id: str, text: str = None):
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token or not callback_id:
            return
        payload = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        requests.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json=payload,
            timeout=10,
        )

    def _build_inline_keyboard(alerts):
        keyboard = []
        for a in alerts:
            anchor = a.get("accountId") or a.get("deviceId")
            if not anchor:
                continue
            title = f"{a.get('ruleKey', '')} | {anchor}"
            cb_data = f"assess|{a.get('ruleKey', '')}|{anchor}"
            keyboard.append([{"text": title[:60], "callback_data": cb_data[:60]}])
        return {"inline_keyboard": keyboard} if keyboard else None

    def _handle_telegram_update(update: dict):
        if not update:
            return {"handled": "empty"}

        # Callback query: run assessment on demand
        if "callback_query" in update:
            cb = update["callback_query"]
            chat_id = cb.get("message", {}).get("chat", {}).get("id")
            data = cb.get("data") or ""
            _telegram_answer_callback(cb.get("id"))
            if data.startswith("assess|"):
                parts = data.split("|", 2)
                if len(parts) == 3:
                    rule_key, anchor = parts[1], parts[2]
                    _telegram_send_message(chat_id, f"Running assessment for {rule_key} ({anchor})…")
                    result = run_ai_assessment(rule_key, anchor)
                    caption = result.get("assessment") or "No assessment."
                    img_path = result.get("image_path")
                    if img_path and os.path.exists(img_path):
                        _telegram_send_photo(chat_id, caption[:1000], img_path)
                    else:
                        _telegram_send_message(chat_id, caption[:4000])
            return {"handled": "callback"}

        message = update.get("message")
        if not message:
            return {"handled": "ignored"}

        chat_id = message.get("chat", {}).get("id")
        text = (message.get("text") or "").strip()
        lower = text.lower()

        if lower.startswith("/start"):
            _telegram_send_message(
                chat_id,
                "👋 Fraud agent ready. Send /sweep to scan for unflagged suspects and tap a result to assess.",
            )
            return {"handled": "start"}

        if lower.startswith("/sweep") or lower.startswith("/scan"):
            alerts = compute_ai_top(limit=5, exclude_flagged=True)
            if not alerts:
                _telegram_send_message(chat_id, "No unflagged suspects right now.")
                return {"handled": "sweep-empty"}
            keyboard = _build_inline_keyboard(alerts)
            lines = []
            for a in alerts:
                anchor = a.get("accountId") or a.get("deviceId")
                sev = a.get("severity") or ""
                lines.append(f"{a.get('ruleKey')} [{sev}] {anchor}")
            body = "🔍 Search & Destroy suspects (tap to assess):\n" + "\n".join(lines)
            _telegram_send_message(chat_id, body, reply_markup=keyboard)
            return {"handled": "sweep"}

        _telegram_send_message(chat_id, "Send /sweep to look for unflagged suspects.")
        return {"handled": "fallback"}

    @app.route("/api/telegram/webhook", methods=["POST"])
    def telegram_webhook():
        secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        provided = request.args.get("token") or request.headers.get("X-Telegram-Token")
        if secret and provided != secret:
            return jsonify({"status": "error", "message": "Unauthorized"}), 403
        try:
            update = request.get_json(force=True) or {}
        except Exception:
            update = {}
        try:
            result = _handle_telegram_update(update)
            return jsonify({"status": "ok", "result": result})
        except Exception as exc:
            print(f"[TELEGRAM-WEBHOOK] error: {exc}")
            return jsonify({"status": "error", "message": str(exc)}), 500

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
