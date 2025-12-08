from flask import Blueprint, jsonify, request, abort
from sqlalchemy import select, case, desc

from backend.db.session import get_session
from backend.models import Alert, RuleDefinition, Case, Account
from backend.services.rule_executor import refresh_alerts

alerts_bp = Blueprint("alerts", __name__)

SEVERITY_ORDER = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
}


@alerts_bp.route("/alerts/refresh", methods=["POST"])
def run_alerts_refresh():
    payload = request.get_json(silent=True) or {}
    rule_id = payload.get("rule_id")
    generated = refresh_alerts(rule_id=rule_id)
    return jsonify({"status": "ok", "generated_alerts": generated})


@alerts_bp.route("/alerts", methods=["GET"])
def list_alerts():
    status_filter = request.args.get("status")
    family_filter = request.args.get("family")
    session = get_session()
    try:
        severity_order = case(
            (Alert.severity == "CRITICAL", 4),
            (Alert.severity == "HIGH", 3),
            (Alert.severity == "MEDIUM", 2),
            else_=1,
        )
        query = (
            select(Alert, RuleDefinition.name, Account.account_number)
            .join(RuleDefinition, Alert.rule_id == RuleDefinition.id)
            .join(Account, Alert.subject_account_id == Account.id, isouter=True)
            .order_by(desc(severity_order), Alert.created_at.desc())
        )
        if status_filter:
            query = query.where(Alert.status == status_filter)
        if family_filter and family_filter.upper() == "FAF":
            query = query.where(RuleDefinition.name.like("FAF-%"))

        results = session.execute(query).all()
        alerts = []
        for alert, rule_name, account_number in results:
            alerts.append(
                {
                    "id": alert.id,
                    "rule_name": rule_name,
                    "ruleKey": rule_name,
                    "accountId": account_number,
                    "severity": alert.severity,
                    "status": alert.status,
                    "summary": alert.summary,
                    "is_afasa": alert.is_afasa,
                    "afasa_suspicion_type": alert.afasa_suspicion_type,
                    "afasa_risk_score": alert.afasa_risk_score,
                    "created_at": alert.created_at.isoformat() if alert.created_at else None,
                }
            )
        return jsonify(alerts)
    finally:
        session.close()


@alerts_bp.route("/alerts/<int:alert_id>", methods=["GET"])
def get_alert(alert_id: int):
    session = get_session()
    try:
        alert = session.execute(select(Alert).where(Alert.id == alert_id)).scalar_one_or_none()
        if not alert:
            abort(404, description="Alert not found")
        case_obj = session.execute(select(Case).where(Case.alert_id == alert.id)).scalar_one_or_none()

        alert_data = {
            "id": alert.id,
            "rule_id": alert.rule_id,
            "severity": alert.severity,
            "status": alert.status,
            "summary": alert.summary,
            "details": alert.details,
            "is_afasa": alert.is_afasa,
            "afasa_suspicion_type": alert.afasa_suspicion_type,
            "afasa_risk_score": alert.afasa_risk_score,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "updated_at": alert.updated_at.isoformat() if alert.updated_at else None,
        }

        case_data = None
        if case_obj:
            case_data = {
                "id": case_obj.id,
                "status": case_obj.status,
                "subject_account": {
                    "id": case_obj.subject_account.id if case_obj.subject_account else None,
                    "account_number": case_obj.subject_account.account_number if case_obj.subject_account else None,
                    "customer_name": case_obj.subject_account.customer_name if case_obj.subject_account else None,
                },
                "network_summary": case_obj.network_summary,
                "linked_accounts": case_obj.linked_accounts or [],
                "linked_devices": case_obj.linked_devices or [],
                "created_at": case_obj.created_at.isoformat() if case_obj.created_at else None,
                "updated_at": case_obj.updated_at.isoformat() if case_obj.updated_at else None,
            }

        return jsonify({"alert": alert_data, "case": case_data})
    finally:
        session.close()
