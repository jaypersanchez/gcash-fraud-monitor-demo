from flask import Blueprint, jsonify, request, abort
from sqlalchemy import select

from backend.db.session import get_session
from backend.models import Case
from backend.services.case_service import add_case_action, list_actions

cases_bp = Blueprint("cases", __name__)


@cases_bp.route("/cases/<int:case_id>/actions", methods=["POST"])
def create_case_action(case_id: int):
    payload = request.get_json(force=True)
    action = payload.get("action")
    notes = payload.get("notes")
    performed_by = payload.get("performed_by")

    case = add_case_action(case_id, action, performed_by=performed_by, notes=notes)
    if case is None:
        abort(404, description="Case not found")

    case_data = {
        "id": case.id,
        "status": case.status,
        "network_summary": case.network_summary,
        "linked_accounts": case.linked_accounts or [],
        "linked_devices": case.linked_devices or [],
    }
    return jsonify({"status": "ok", "case": case_data})


@cases_bp.route("/cases/<int:case_id>/audit", methods=["GET"])
def get_audit(case_id: int):
    actions = list_actions(case_id)
    return jsonify(
        [
            {
                "id": action.id,
                "action": action.action,
                "performed_by": action.performed_by,
                "notes": action.notes,
                "created_at": action.created_at.isoformat() if action.created_at else None,
            }
            for action in actions
        ]
    )
