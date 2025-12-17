from flask import Blueprint, jsonify, request

from backend.services.analytics_service import get_dashboard_data

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics/dashboard", methods=["GET"])
def analytics_dashboard():
    time_range = request.args.get("time_range", "24h")
    severity = request.args.get("severity", "all")
    rule_id = request.args.get("rule_id", "all")

    data = get_dashboard_data(time_range=time_range, severity=severity, rule_id=rule_id)
    return jsonify(data)
