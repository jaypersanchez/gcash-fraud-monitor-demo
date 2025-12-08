from flask import Blueprint, jsonify, request, abort
from sqlalchemy import select

from backend.db.session import get_session
from backend.afasa.models import AfasaDisputedTransaction
from backend.afasa.schemas import disputed_transaction_to_dict, verification_event_to_dict
from backend.afasa.services import (
    initiate_disputed_transaction,
    apply_temporary_hold,
    release_or_restitute_funds,
    add_verification_event,
)
from backend.models.alert import Alert


afasa_bp = Blueprint("afasa", __name__)


@afasa_bp.route("/afasa/disputes", methods=["POST"])
def create_dispute():
    payload = request.get_json(force=True)
    alert_id = payload.get("alert_id")
    tx_id = payload.get("tx_id")
    reason_category = payload.get("reason_category")
    suspicion_type = payload.get("suspicion_type")
    actor = payload.get("initiated_by", "system")
    session = get_session()
    try:
        dispute = initiate_disputed_transaction(
            session,
            alert_id=alert_id,
            tx_id=tx_id,
            reason_category=reason_category,
            suspicion_type=suspicion_type,
            initiated_by=actor,
        )
        return jsonify(disputed_transaction_to_dict(dispute)), 201
    except Exception as exc:
        session.rollback()
        abort(400, description=str(exc))
    finally:
        session.close()


@afasa_bp.route("/afasa/disputes", methods=["GET"])
def list_disputes():
    status_filter = request.args.get("status")
    suspicion_filter = request.args.get("suspicion_type")
    session = get_session()
    try:
        query = select(AfasaDisputedTransaction)
        if status_filter:
            query = query.where(AfasaDisputedTransaction.status == status_filter)
        if suspicion_filter:
            query = query.where(AfasaDisputedTransaction.suspicion_type == suspicion_filter)
        rows = session.execute(query).scalars().all()
        return jsonify([disputed_transaction_to_dict(row) for row in rows])
    finally:
        session.close()


@afasa_bp.route("/afasa/disputes/<int:dispute_id>", methods=["GET"])
def get_dispute(dispute_id: int):
    session = get_session()
    try:
        dispute = session.get(AfasaDisputedTransaction, dispute_id)
        if not dispute:
            abort(404, description="Dispute not found")
        return jsonify(disputed_transaction_to_dict(dispute))
    finally:
        session.close()


@afasa_bp.route("/afasa/disputes/<int:dispute_id>/hold", methods=["POST"])
def hold_dispute(dispute_id: int):
    actor = (request.get_json(silent=True) or {}).get("actor", "system")
    session = get_session()
    try:
        dispute = apply_temporary_hold(session, dispute_id, actor)
        return jsonify(disputed_transaction_to_dict(dispute))
    except Exception as exc:
        session.rollback()
        abort(400, description=str(exc))
    finally:
        session.close()


@afasa_bp.route("/afasa/disputes/<int:dispute_id>/release", methods=["POST"])
def release_dispute(dispute_id: int):
    payload = request.get_json(force=True)
    decision = payload.get("decision", "RELEASE")
    notes = payload.get("notes")
    actor = payload.get("actor", "system")
    session = get_session()
    try:
        dispute = release_or_restitute_funds(session, dispute_id, decision, actor, notes)
        return jsonify(disputed_transaction_to_dict(dispute))
    except Exception as exc:
        session.rollback()
        abort(400, description=str(exc))
    finally:
        session.close()


@afasa_bp.route("/afasa/disputes/<int:dispute_id>/events", methods=["POST"])
def add_event(dispute_id: int):
    payload = request.get_json(force=True)
    evt_type = payload.get("event_type")
    notes = payload.get("notes")
    actor = payload.get("actor", "system")
    session = get_session()
    try:
        event = add_verification_event(session, dispute_id, evt_type, notes, actor)
        return jsonify(verification_event_to_dict(event)), 201
    except Exception as exc:
        session.rollback()
        abort(400, description=str(exc))
    finally:
        session.close()


@afasa_bp.route("/afasa/reports/summary", methods=["GET"])
def report_summary():
    session = get_session()
    try:
        total = session.execute(select(AfasaDisputedTransaction)).scalars().all()
        summary = {
            "total_disputes": len(total),
            "by_status": {},
            "by_suspicion": {},
        }
        for d in total:
            summary["by_status"][d.status] = summary["by_status"].get(d.status, 0) + 1
            summary["by_suspicion"][d.suspicion_type] = summary["by_suspicion"].get(d.suspicion_type, 0) + 1
        return jsonify(summary)
    finally:
        session.close()


@afasa_bp.route("/afasa/reports/case/<int:dispute_id>", methods=["GET"])
def report_case(dispute_id: int):
    session = get_session()
    try:
        dispute = session.get(AfasaDisputedTransaction, dispute_id)
        if not dispute:
            abort(404, description="Dispute not found")
        alert = session.get(Alert, dispute.alert_id) if dispute.alert_id else None
        return jsonify(
            {
                "dispute": disputed_transaction_to_dict(dispute),
                "alert": {
                    "id": alert.id,
                    "summary": alert.summary,
                    "afasa_suspicion_type": alert.afasa_suspicion_type,
                    "afasa_risk_score": alert.afasa_risk_score,
                }
                if alert
                else None,
            }
        )
    finally:
        session.close()
