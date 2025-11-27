from flask import Blueprint, jsonify

from backend.services.neo4j_client import check_connectivity, get_driver

neo4j_bp = Blueprint("neo4j", __name__)


@neo4j_bp.route("/neo4j/health", methods=["GET"])
def neo4j_health():
    try:
        result = check_connectivity()
        return jsonify({"status": "ok", "result": result})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@neo4j_bp.route("/neo4j/graph/account/<account_id>", methods=["GET"])
def neo4j_graph_account(account_id: str):
    cypher = """
    MATCH (a:Account {account_number: $accountId})
    OPTIONAL MATCH (a)-[:USES]->(d:Device)
    OPTIONAL MATCH (d)<-[:USES]-(devAcc:Account)
    OPTIONAL MATCH (a)-[:PERFORMS]->(txOut:Transaction)-[:TO]->(dst:Account)
    OPTIONAL MATCH (src:Account)-[:PERFORMS]->(txIn:Transaction)-[:TO]->(a)
    RETURN a,
           collect(DISTINCT d) AS devices,
           collect(DISTINCT devAcc) AS device_accounts,
           collect(DISTINCT {tx: txOut, other: dst, direction: 'OUT'}) AS outbound,
           collect(DISTINCT {tx: txIn, other: src, direction: 'IN'}) AS inbound
    """
    with get_driver() as driver:
        with driver.session() as session:
            record = session.run(cypher, accountId=account_id).single()
            if not record:
                return jsonify({"status": "error", "message": "Account not found"}), 404

            nodes = {}
            edges = []

            def add_node(key, label, ntype, extra=None):
                if key in nodes:
                    return
                node = {"id": key, "label": label, "type": ntype}
                if extra:
                    node.update(extra)
                nodes[key] = node

            a = record["a"]
            add_node(a["account_number"], a["account_number"], "Account", {"customerName": a.get("customer_name"), "isSubject": True})

            for dev in record["devices"] or []:
                add_node(dev["device_id"], dev["device_id"], "Device", {"deviceType": dev.get("device_type")})
                edges.append({"source": a["account_number"], "target": dev["device_id"], "type": "USES"})

            for acc in record["device_accounts"] or []:
                add_node(acc["account_number"], acc["account_number"], "Account", {"customerName": acc.get("customer_name")})
                edges.append({"source": acc["account_number"], "target": a["account_number"], "type": "SHARES_DEVICE"})

            def handle_tx(items):
                for item in items or []:
                    tx = item.get("tx")
                    other = item.get("other")
                    direction = item.get("direction")
                    if not tx or not other:
                        continue
                    tx_ref = tx["tx_ref"]
                    add_node(tx_ref, tx_ref, "Transaction", {"amount": tx.get("amount"), "tags": tx.get("tags")})
                    add_node(other["account_number"], other["account_number"], "Account", {"customerName": other.get("customer_name")})
                    if direction == "OUT":
                        edges.append({"source": a["account_number"], "target": tx_ref, "type": "PERFORMS", "label": _edge_label(tx)})
                        edges.append({"source": tx_ref, "target": other["account_number"], "type": "TO"})
                    else:
                        edges.append({"source": other["account_number"], "target": tx_ref, "type": "PERFORMS", "label": _edge_label(tx)})
                        edges.append({"source": tx_ref, "target": a["account_number"], "type": "TO"})

            handle_tx(record.get("outbound"))
            handle_tx(record.get("inbound"))

    return jsonify({"status": "ok", "nodes": list(nodes.values()), "edges": edges})


def _edge_label(tx):
    parts = []
    amount = tx.get("amount")
    tags = tx.get("tags")
    if amount is not None:
        parts.append(f"{amount}")
    if tags:
        parts.append(str(tags))
    return " / ".join(parts)


@neo4j_bp.route("/neo4j/graph/device/<device_id>", methods=["GET"])
def neo4j_graph_device(device_id: str):
    cypher = """
    MATCH (d:Device {device_id: $deviceId})
    OPTIONAL MATCH (d)<-[:USES]-(a:Account)
    OPTIONAL MATCH (a)-[:PERFORMS]->(txOut:Transaction)-[:TO]->(dst:Account)
    OPTIONAL MATCH (src:Account)-[:PERFORMS]->(txIn:Transaction)-[:TO]->(a)
    RETURN d,
           collect(DISTINCT a) AS accounts,
           collect(DISTINCT {tx: txOut, other: dst, direction: 'OUT'}) AS outbound,
           collect(DISTINCT {tx: txIn, other: src, direction: 'IN'}) AS inbound
    """
    with get_driver() as driver:
        with driver.session() as session:
            record = session.run(cypher, deviceId=device_id).single()
            if not record:
                return jsonify({"status": "error", "message": "Device not found"}), 404

            nodes = {}
            edges = []

            def add_node(key, label, ntype, extra=None):
                if key in nodes:
                    return
                node = {"id": key, "label": label, "type": ntype}
                if extra:
                    node.update(extra)
                nodes[key] = node

            d = record["d"]
            add_node(d["device_id"], d["device_id"], "Device", {"deviceType": d.get("device_type"), "isSubject": True})

            for acc in record["accounts"] or []:
                add_node(acc["account_number"], acc["account_number"], "Account", {"customerName": acc.get("customer_name")})
                edges.append({"source": acc["account_number"], "target": d["device_id"], "type": "USES"})

            def handle_tx(items):
                for item in items or []:
                    tx = item.get("tx")
                    other = item.get("other")
                    direction = item.get("direction")
                    if not tx or not other:
                        continue
                    tx_ref = tx["tx_ref"]
                    add_node(tx_ref, tx_ref, "Transaction", {"amount": tx.get("amount"), "tags": tx.get("tags")})
                    add_node(other["account_number"], other["account_number"], "Account", {"customerName": other.get("customer_name")})
                    if direction == "OUT":
                        edges.append({"source": other["account_number"], "target": tx_ref, "type": "PERFORMS", "label": _edge_label(tx)})
                        edges.append({"source": tx_ref, "target": other["account_number"], "type": "TO"})
                    else:
                        edges.append({"source": other["account_number"], "target": tx_ref, "type": "PERFORMS", "label": _edge_label(tx)})
                        edges.append({"source": tx_ref, "target": d["device_id"], "type": "TO"})

            handle_tx(record.get("outbound"))
            handle_tx(record.get("inbound"))

    return jsonify({"status": "ok", "nodes": list(nodes.values()), "edges": edges})
