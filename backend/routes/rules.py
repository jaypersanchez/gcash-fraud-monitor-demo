from flask import Blueprint, jsonify, abort
from sqlalchemy import select

from backend.db.session import get_session
from backend.models import RuleDefinition

rules_bp = Blueprint("rules", __name__)


@rules_bp.route("/rules", methods=["GET"])
def list_rules():
    session = get_session()
    try:
        rules = session.execute(select(RuleDefinition)).scalars().all()
        return jsonify(
            [
                {
                    "id": rule.id,
                    "name": rule.name,
                    "description": rule.description,
                    "cypher_query": rule.cypher_query,
                    "severity": rule.severity,
                    "enabled": rule.enabled,
                    "created_at": rule.created_at.isoformat() if rule.created_at else None,
                }
                for rule in rules
            ]
        )
    finally:
        session.close()


@rules_bp.route("/rules/<int:rule_id>", methods=["GET"])
def get_rule(rule_id: int):
    session = get_session()
    try:
        rule = session.execute(select(RuleDefinition).where(RuleDefinition.id == rule_id)).scalar_one_or_none()
        if not rule:
            abort(404, description="Rule not found")
        return jsonify(
            {
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "cypher_query": rule.cypher_query,
                "severity": rule.severity,
                "enabled": rule.enabled,
                "created_at": rule.created_at.isoformat() if rule.created_at else None,
            }
        )
    finally:
        session.close()
