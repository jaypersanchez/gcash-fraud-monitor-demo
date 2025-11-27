from flask import Blueprint, jsonify, request

from backend.db.session import get_session
from backend.models import InvestigatorAction

investigator_bp = Blueprint("investigator", __name__)


@investigator_bp.route("/investigator/notes", methods=["POST"])
def add_note():
    payload = request.get_json(force=True)
    anchor_id = payload.get("anchor_id")
    anchor_type = payload.get("anchor_type", "ACCOUNT")
    rule_key = payload.get("rule_key")
    note = payload.get("note")
    if not anchor_id or not note:
        return jsonify({"status": "error", "message": "anchor_id and note are required"}), 400
    session = get_session()
    try:
        action = InvestigatorAction(
            anchor_id=anchor_id,
            anchor_type=anchor_type,
            action="NOTE",
            status=None,
            note=note,
            rule_key=rule_key,
        )
        session.add(action)
        session.commit()
        return jsonify({"status": "ok", "id": action.id, "created_at": action.created_at.isoformat()})
    except Exception as exc:
        session.rollback()
        return jsonify({"status": "error", "message": str(exc)}), 500
    finally:
        session.close()


@investigator_bp.route("/investigator/actions", methods=["POST"])
def add_action():
    payload = request.get_json(force=True)
    anchor_id = payload.get("anchor_id")
    anchor_type = payload.get("anchor_type", "ACCOUNT")
    rule_key = payload.get("rule_key")
    action_type = payload.get("action")
    status = payload.get("status")
    note = payload.get("note")
    if not anchor_id or not action_type:
        return jsonify({"status": "error", "message": "anchor_id and action are required"}), 400
    session = get_session()
    try:
        action = InvestigatorAction(
            anchor_id=anchor_id,
            anchor_type=anchor_type,
            action=action_type,
            status=status,
            note=note,
            rule_key=rule_key,
        )
        session.add(action)
        session.commit()
        return jsonify({"status": "ok", "id": action.id, "created_at": action.created_at.isoformat()})
    except Exception as exc:
        session.rollback()
        return jsonify({"status": "error", "message": str(exc)}), 500
    finally:
        session.close()
