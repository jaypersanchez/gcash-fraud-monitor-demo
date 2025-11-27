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
    WITH a, collect(DISTINCT d) AS devices
    OPTIONAL MATCH (a)-[:PERFORMS]->(t:Transaction)-[:TO]->(b:Account)
    RETURN a, devices, collect(DISTINCT {tx: t, to: b}) AS tx_edges
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

            for item in record["tx_edges"] or []:
                tx = item.get("tx")
                dest = item.get("to")
                if not tx or not dest:
                    continue
                tx_ref = tx["tx_ref"]
                add_node(tx_ref, tx_ref, "Transaction", {"amount": tx.get("amount"), "tags": tx.get("tags")})
                add_node(dest["account_number"], dest["account_number"], "Account", {"customerName": dest.get("customer_name")})
                edges.append({"source": a["account_number"], "target": tx_ref, "type": "PERFORMS"})
                edges.append({"source": tx_ref, "target": dest["account_number"], "type": "TO"})

    return jsonify({"status": "ok", "nodes": list(nodes.values()), "edges": edges})
