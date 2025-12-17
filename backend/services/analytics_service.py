from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import case, func, select

from backend.db.session import get_session
from backend.models import Alert, Case, RuleDefinition
from backend.services.neo4j_client import get_read_session

# Simple in-memory cache for demo responsiveness
_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 10
OPEN_STATUSES = ("OPEN", "IN_PROGRESS")


def _cache_key(time_range: str, severity: str, rule_id: str) -> str:
    return f"{time_range}|{severity}|{rule_id}"


def parse_time_range(value: Optional[str]) -> datetime:
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    if not value:
        return now - timedelta(hours=24)
    value = value.lower()
    if value.endswith("h"):
        try:
            hours = int(value[:-1])
            return now - timedelta(hours=hours)
        except ValueError:
            return now - timedelta(hours=24)
    if value.endswith("d"):
        try:
            days = int(value[:-1])
            return now - timedelta(days=days)
        except ValueError:
            return now - timedelta(hours=24)
    return now - timedelta(hours=24)


def _resolve_rule_filter(session, rule_id: str):
    if not rule_id or rule_id == "all":
        return None
    try:
        return int(rule_id)
    except ValueError:
        rule = session.execute(select(RuleDefinition).where(RuleDefinition.name == rule_id)).scalar_one_or_none()
        return rule.id if rule else None


def _alerts_base_filters(cutoff: datetime, severity: str, rule_filter: Optional[int]):
    filters = [Alert.created_at >= cutoff]
    if severity and severity.lower() != "all":
        filters.append(Alert.severity == severity.upper())
    if rule_filter is not None:
        filters.append(Alert.rule_id == rule_filter)
    return filters


def _group_granularity(time_range: str) -> str:
    if time_range:
        try:
            if time_range.endswith("h") and int(time_range[:-1]) <= 24:
                return "hour"
        except ValueError:
            pass
    return "day"


def _fetch_postgres_metrics(time_range: str, severity: str, rule_id: str, cutoff: datetime) -> Dict[str, Any]:
    session = get_session()
    try:
        rule_filter = _resolve_rule_filter(session, rule_id)
        filters = _alerts_base_filters(cutoff, severity, rule_filter)

        alerts_total = session.scalar(select(func.count(Alert.id)).where(*filters)) or 0
        alerts_open = session.scalar(select(func.count(Alert.id)).where(*filters, Alert.status.in_(OPEN_STATUSES))) or 0
        cases_open = session.scalar(select(func.count(Case.id)).where(Case.created_at >= cutoff, Case.status.in_(OPEN_STATUSES))) or 0

        granularity = _group_granularity(time_range)
        ts_bucket = func.date_trunc(granularity, Alert.created_at)
        alerts_by_time = (
            session.execute(
                select(ts_bucket.label("bucket"), func.count(Alert.id).label("count"))
                .where(*filters)
                .group_by(ts_bucket)
                .order_by(ts_bucket)
            ).all()
        )
        alerts_by_hour = []
        for row in alerts_by_time:
            bucket = row.bucket
            if bucket and bucket.tzinfo is None:
                bucket = bucket.replace(tzinfo=timezone.utc)
            alerts_by_hour.append({"ts": bucket.isoformat() if bucket else None, "count": row.count})

        severity_distribution = (
            session.execute(
                select(Alert.severity, func.count(Alert.id))
                .where(*filters)
                .group_by(Alert.severity)
                .order_by(
                    case(
                        (Alert.severity == "CRITICAL", 4),
                        (Alert.severity == "HIGH", 3),
                        (Alert.severity == "MEDIUM", 2),
                        else_=1,
                    ).desc()
                )
            ).all()
        )
        alerts_by_severity = [{"severity": sev, "count": count} for sev, count in severity_distribution]

        rule_hits_rows = (
            session.execute(
                select(Alert.rule_id, RuleDefinition.name, func.count(Alert.id))
                .join(RuleDefinition, Alert.rule_id == RuleDefinition.id)
                .where(*filters)
                .group_by(Alert.rule_id, RuleDefinition.name)
                .order_by(func.count(Alert.id).desc())
            ).all()
        )
        rule_hits = []
        for r_id, rule_name, count in rule_hits_rows:
            label = rule_name or (f"Rule {r_id}" if r_id is not None else "Unknown")
            rule_hits.append({"rule_id": label, "count": count})

        return {
            "kpis": {
                "alerts_total": alerts_total,
                "alerts_open": alerts_open,
                "cases_open": cases_open,
            },
            "charts": {
                "alerts_by_hour": alerts_by_hour,
                "alerts_by_severity": alerts_by_severity,
                "rule_hits": rule_hits,
            },
        }
    finally:
        session.close()


def _fetch_neo4j_metrics(cutoff: datetime) -> Dict[str, Any]:
    try:
        with get_read_session() as session:
            suspects_flagged = session.run(
                """
                MATCH (a:Account)
                WHERE coalesce(a.flagged, false) = true
                   OR coalesce(a.risk_score, 0) >= 80
                RETURN count(a) AS suspects_flagged
                """
            ).single()["suspects_flagged"]

            top_suspects_records = session.run(
                """
                MATCH (a:Account)
                OPTIONAL MATCH (a)-[r]-()
                WITH a, count(r) AS degree
                RETURN
                    coalesce(a.account_id, coalesce(a.account_number, toString(id(a)))) AS id,
                    coalesce(a.risk_score, 0) AS risk_score,
                    coalesce(a.flags, 0) AS flags,
                    coalesce(a.last_seen, "") AS last_seen,
                    degree
                ORDER BY risk_score DESC, degree DESC
                LIMIT 10
                """
            ).data()

            rule_hits_records = session.run(
                """
                MATCH (al:Alert)
                RETURN coalesce(al.rule_id, 'Unknown') AS rule_id, count(*) AS count
                ORDER BY count DESC
                LIMIT 10
                """
            ).data()

            top_suspects = [
                {
                    "id": rec.get("id"),
                    "risk_score": rec.get("risk_score", 0),
                    "flags": rec.get("flags", 0),
                    "last_seen": rec.get("last_seen", ""),
                    "degree": rec.get("degree", 0),
                }
                for rec in top_suspects_records
            ]

            return {
                "kpis": {"suspects_flagged": suspects_flagged or 0},
                "charts": {"rule_hits": rule_hits_records},
                "tables": {"top_suspects": top_suspects},
            }
    except Exception:
        # Neo4j may be offline; fall back gracefully.
        return {"kpis": {"suspects_flagged": 0}, "charts": {"rule_hits": []}, "tables": {"top_suspects": []}}


def get_dashboard_data(time_range: str = "24h", severity: str = "all", rule_id: str = "all") -> Dict[str, Any]:
    key = _cache_key(time_range, severity, rule_id)
    now = datetime.utcnow()
    cached = _CACHE.get(key)
    if cached and cached["expires_at"] > now:
        return cached["data"]

    cutoff = parse_time_range(time_range)
    pg_metrics = _fetch_postgres_metrics(time_range, severity, rule_id, cutoff)
    neo_metrics = _fetch_neo4j_metrics(cutoff)

    merged_rule_hits = pg_metrics["charts"]["rule_hits"] or neo_metrics["charts"].get("rule_hits", [])
    response = {
        "kpis": {
            "alerts_total": pg_metrics["kpis"]["alerts_total"],
            "alerts_open": pg_metrics["kpis"]["alerts_open"],
            "cases_open": pg_metrics["kpis"]["cases_open"],
            "suspects_flagged": neo_metrics["kpis"].get("suspects_flagged", 0),
        },
        "charts": {
            "alerts_by_hour": pg_metrics["charts"]["alerts_by_hour"],
            "alerts_by_severity": pg_metrics["charts"]["alerts_by_severity"],
            "rule_hits": merged_rule_hits,
        },
        "tables": {
            "top_suspects": neo_metrics["tables"].get("top_suspects", []),
        },
    }

    _CACHE[key] = {"data": response, "expires_at": now + timedelta(seconds=_CACHE_TTL_SECONDS)}
    return response
