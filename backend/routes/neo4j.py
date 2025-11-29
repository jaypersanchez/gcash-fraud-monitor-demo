from flask import Blueprint, jsonify

from backend.services.neo4j_client import check_connectivity, get_driver
from backend.db.session import get_session
from backend.models.investigator_action import InvestigatorAction

neo4j_bp = Blueprint("neo4j", __name__)


@neo4j_bp.route("/neo4j/health", methods=["GET"])
def neo4j_health():
    try:
        result = check_connectivity()
        return jsonify({"status": "ok", "result": result})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


def _record_flag(anchor_id: str, anchor_type: str):
    session = get_session()
    try:
        action = InvestigatorAction(
            anchor_id=anchor_id,
            anchor_type=anchor_type,
            action="FLAG",
            status="FLAGGED",
        )
        session.add(action)
        session.commit()
    finally:
        session.close()


def _flagged_map(anchor_ids, anchor_type: str):
    if not anchor_ids:
        return set()
    session = get_session()
    try:
        rows = (
            session.query(InvestigatorAction.anchor_id)
            .filter(
                InvestigatorAction.anchor_id.in_(list(anchor_ids)),
                InvestigatorAction.anchor_type == anchor_type,
                InvestigatorAction.action == "FLAG",
            )
            .all()
        )
        return {r.anchor_id for r in rows}
    finally:
        session.close()


def _is_flagged(node: dict, labels=None):
    labels = labels or []
    if "Mule" in labels:
        return True
    if node.get("fraud_group") is not None:
        return True
    if node.get("flagged") is True:
        return True
    val = node.get("is_fraud")
    if isinstance(val, str):
        val = val.lower() in {"true", "1", "yes"}
    return bool(val)


@neo4j_bp.route("/neo4j/flag/account/<account_id>", methods=["POST"])
def neo4j_flag_account(account_id: str):
    # Persist flag in Postgres so we don't rely on mutating remote Neo4j
    _record_flag(account_id, "ACCOUNT")
    # Best-effort: try to set a flag property in Neo4j, but ignore failures
    cypher = """
    MATCH (a)
    WHERE (a:Account AND a.account_number = $accountId)
       OR (a:Mule AND a.id = $accountId)
       OR (a:Client AND a.id = $accountId)
    SET a.flagged = true, a.flagged_at = datetime()
    RETURN coalesce(a.account_number, a.id) AS accountId
    """
    try:
        with get_driver() as driver:
            with driver.session() as session:
                session.run(cypher, accountId=account_id).consume()
    except Exception:
        pass
    return jsonify({"status": "ok", "accountId": account_id})


@neo4j_bp.route("/neo4j/flag/device/<device_id>", methods=["POST"])
def neo4j_flag_device(device_id: str):
    _record_flag(device_id, "DEVICE")
    cypher = """
    MATCH (d)
    WHERE (d:Device AND d.device_id = $deviceId)
       OR (d:Email AND d.email = $deviceId)
       OR (d:Phone AND d.phoneNumber = $deviceId)
       OR (d:SSN AND d.ssn = $deviceId)
    SET d.flagged = true, d.flagged_at = datetime()
    RETURN
      CASE
        WHEN d.device_id IS NOT NULL THEN d.device_id
        WHEN d.email IS NOT NULL THEN d.email
        WHEN d.phoneNumber IS NOT NULL THEN d.phoneNumber
        ELSE d.ssn
      END AS deviceId
    """
    try:
        with get_driver() as driver:
            with driver.session() as session:
                session.run(cypher, deviceId=device_id).consume()
    except Exception:
        pass
    return jsonify({"status": "ok", "deviceId": device_id})


@neo4j_bp.route("/neo4j/graph/account/<account_id>", methods=["GET"])
def neo4j_graph_account(account_id: str):
    cypher = """
    MATCH (a)
    WHERE (a:Account AND a.account_number = $accountId)
       OR (a:Mule AND a.id = $accountId)
       OR (a:Client AND a.id = $accountId)
    OPTIONAL MATCH (a)-[r:HAS_EMAIL|HAS_PHONE|HAS_SSN]->(id)<-[r2:HAS_EMAIL|HAS_PHONE|HAS_SSN]-(peer)
    OPTIONAL MATCH (a)-[:PERFORMED]->(txOut:Transaction)-[:TO]->(dst)
    OPTIONAL MATCH (src)-[:PERFORMED]->(txIn:Transaction)-[:TO]->(a)
    RETURN a,
           labels(a) AS a_labels,
           collect(DISTINCT id) AS identifiers,
           collect(DISTINCT {idNode: id, peer: peer, peerLabels: labels(peer)}) AS idPeers,
           collect(DISTINCT {tx: txOut, other: dst, otherLabels: labels(dst), direction: 'OUT'}) AS outbound,
           collect(DISTINCT {tx: txIn, other: src, otherLabels: labels(src), direction: 'IN'}) AS inbound
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
            anchor_id = a.get("account_number") or a.get("id")
            anchor_label = a.get("customer_name") or a.get("name") or anchor_id
            anchor_labels = record.get("a_labels") or []
            flagged_anchor = _is_flagged(a, anchor_labels)
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
                flagged_id = _is_flagged(id_node)
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
                flagged_peer = _is_flagged(peer, peer_labels)
                add_node(peer_id, peer_label, "Account", {"customerName": peer_label, "isFlagged": flagged_peer})
                flagged_id = _is_flagged(id_node)
                add_node(device_id, device_id, "Device", {"deviceType": "Identifier", "isFlagged": flagged_id})
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
                    flagged_other = _is_flagged(other, other_labels)
                    add_node(other_id, other_label, "Account", {"customerName": other_label, "isFlagged": flagged_other})
                    if direction == "OUT":
                        edges.append({"source": anchor_id, "target": tx_ref, "type": "PERFORMS", "label": _edge_label(tx)})
                        edges.append({"source": tx_ref, "target": other_id, "type": "TO"})
                    else:
                        edges.append({"source": other_id, "target": tx_ref, "type": "PERFORMS", "label": _edge_label(tx)})
                        edges.append({"source": tx_ref, "target": anchor_id, "type": "TO"})

            handle_tx(record.get("outbound"))
            handle_tx(record.get("inbound"))

    # Overlay flags from Postgres
    account_ids = [n["id"] for n in nodes.values() if n["type"] == "Account"]
    device_ids = [n["id"] for n in nodes.values() if n["type"] == "Device"]
    flagged_accounts = _flagged_map(account_ids, "ACCOUNT")
    flagged_devices = _flagged_map(device_ids, "DEVICE")
    for n in nodes.values():
        if n["id"] in flagged_accounts or n["id"] in flagged_devices:
            n["isFlagged"] = True

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
    MATCH (id)
    WHERE (id:Device AND id.device_id = $deviceId)
       OR (id:Email AND id.email = $deviceId)
       OR (id:Phone AND id.phoneNumber = $deviceId)
       OR (id:SSN AND id.ssn = $deviceId)
    OPTIONAL MATCH (id)<-[:HAS_EMAIL|HAS_PHONE|HAS_SSN]-(a)
    OPTIONAL MATCH (a)-[:PERFORMED]->(txOut:Transaction)-[:TO]->(dst)
    OPTIONAL MATCH (src)-[:PERFORMED]->(txIn:Transaction)-[:TO]->(a)
    RETURN id,
           collect(DISTINCT {acc: a, accLabels: labels(a)}) AS accounts,
           collect(DISTINCT {tx: txOut, other: dst, otherLabels: labels(dst), direction: 'OUT', acc: a, accLabels: labels(a)}) AS outbound,
           collect(DISTINCT {tx: txIn, other: src, otherLabels: labels(src), direction: 'IN', acc: a, accLabels: labels(a)}) AS inbound
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

            d = record["id"]
            device_id_val = d.get("device_id") or d.get("email") or d.get("phoneNumber") or d.get("ssn")
            device_type = "Device"
            if "email" in d:
                device_type = "Email"
            elif "phoneNumber" in d:
                device_type = "Phone"
            elif "ssn" in d:
                device_type = "SSN"
            flagged_id = _is_flagged(d)
            add_node(device_id_val, device_id_val, "Device", {"deviceType": device_type, "isSubject": True, "isFlagged": flagged_id})

            for acc_entry in record["accounts"] or []:
                acc = acc_entry.get("acc") or {}
                acc_labels = acc_entry.get("accLabels") or []
                acc_id = acc.get("account_number") or acc.get("id")
                acc_label = acc.get("customer_name") or acc.get("name") or acc_id
                flagged_acc = _is_flagged(acc, acc_labels)
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
                    flagged_acc = _is_flagged(acc, acc_labels)
                    add_node(other_id, other_label, "Account", {"customerName": other_label})
                    add_node(acc_id, acc_label, "Account", {"customerName": acc_label, "isFlagged": flagged_acc})
                    if direction == "OUT":
                        edges.append({"source": acc_id, "target": tx_ref, "type": "PERFORMS", "label": _edge_label(tx)})
                        edges.append({"source": tx_ref, "target": other_id, "type": "TO"})
                    else:
                        edges.append({"source": other_id, "target": tx_ref, "type": "PERFORMS", "label": _edge_label(tx)})
                        edges.append({"source": tx_ref, "target": acc_id, "type": "TO"})

            handle_tx(record.get("outbound"))
            handle_tx(record.get("inbound"))

    # Overlay flags from Postgres
    account_ids = [n["id"] for n in nodes.values() if n["type"] == "Account"]
    device_ids = [n["id"] for n in nodes.values() if n["type"] == "Device"]
    flagged_accounts = _flagged_map(account_ids, "ACCOUNT")
    flagged_devices = _flagged_map(device_ids, "DEVICE")
    for n in nodes.values():
        if n["id"] in flagged_accounts or n["id"] in flagged_devices:
            n["isFlagged"] = True

    return jsonify({"status": "ok", "nodes": list(nodes.values()), "edges": edges})


@neo4j_bp.route("/neo4j/graph/identifier/<identifier>", methods=["GET"])
def neo4j_graph_identifier(identifier: str):
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
    with get_driver() as driver:
        with driver.session() as session:
            record = session.run(cypher, identifier=identifier).single()
            if not record:
                return jsonify({"status": "error", "message": "Identifier not found"}), 404

            nodes = {}
            edges = []

            def add_node(key, label, ntype, extra=None):
                if key in nodes:
                    return
                node = {"id": key, "label": label, "type": ntype}
                if extra:
                    node.update(extra)
                nodes[key] = node

            id_node = record["id"]
            device_id_val = id_node.get("device_id") or id_node.get("email") or id_node.get("phoneNumber") or id_node.get("ssn")
            device_type = "Device"
            if "email" in id_node:
                device_type = "Email"
            elif "phoneNumber" in id_node:
                device_type = "Phone"
            elif "ssn" in id_node:
                device_type = "SSN"
            add_node(device_id_val, device_id_val, "Device", {"deviceType": device_type, "isSubject": True})

            for acc_entry in record.get("accounts") or []:
                acc = acc_entry.get("acc") or {}
                acc_labels = acc_entry.get("accLabels") or []
                acc_id = acc.get("account_number") or acc.get("id")
                acc_label = acc.get("customer_name") or acc.get("name") or acc_id
                flagged_acc = _is_flagged(acc, acc_labels)
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
                    flagged_acc = _is_flagged(acc, acc_labels)
                    add_node(other_id, other_label, "Account", {"customerName": other_label})
                    add_node(acc_id, acc_label, "Account", {"customerName": acc_label, "isFlagged": flagged_acc})
                    if direction == "OUT":
                        edges.append({"source": acc_id, "target": tx_ref, "type": "PERFORMS", "label": _edge_label(tx)})
                        edges.append({"source": tx_ref, "target": other_id, "type": "TO"})
                    else:
                        edges.append({"source": other_id, "target": tx_ref, "type": "PERFORMS", "label": _edge_label(tx)})
                        edges.append({"source": tx_ref, "target": acc_id, "type": "TO"})

            handle_tx(record.get("outbound"))
            handle_tx(record.get("inbound"))

    # Overlay flags from Postgres
    account_ids = [n["id"] for n in nodes.values() if n["type"] == "Account"]
    device_ids = [n["id"] for n in nodes.values() if n["type"] == "Device"]
    flagged_accounts = _flagged_map(account_ids, "ACCOUNT")
    flagged_devices = _flagged_map(device_ids, "DEVICE")
    for n in nodes.values():
        if n["id"] in flagged_accounts or n["id"] in flagged_devices:
            n["isFlagged"] = True

    return jsonify({"status": "ok", "nodes": list(nodes.values()), "edges": edges})
