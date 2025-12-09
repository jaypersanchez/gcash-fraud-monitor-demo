from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select

from backend.models.transaction import TransactionLog


def detect_money_mule_patterns(session, tx: TransactionLog) -> Dict:
    """Heuristic mule detection using the relational transaction log."""
    if not tx:
        return {"risk": 0, "signals": []}

    window_start = tx.tx_datetime - timedelta(hours=24)
    distinct_senders = session.execute(
        select(func.count(func.distinct(TransactionLog.sender_account_id)))
        .where(
            TransactionLog.receiver_account_id == tx.receiver_account_id,
            TransactionLog.tx_datetime >= window_start,
            TransactionLog.tx_datetime <= tx.tx_datetime,
        )
    ).scalar_one()

    inflow = session.execute(
        select(func.coalesce(func.sum(TransactionLog.amount), 0)).where(
            TransactionLog.receiver_account_id == tx.receiver_account_id,
            TransactionLog.tx_datetime >= window_start,
            TransactionLog.tx_datetime <= tx.tx_datetime,
        )
    ).scalar_one()
    outflow = session.execute(
        select(func.coalesce(func.sum(TransactionLog.amount), 0)).where(
            TransactionLog.sender_account_id == tx.receiver_account_id,
            TransactionLog.tx_datetime >= window_start,
            TransactionLog.tx_datetime <= tx.tx_datetime,
        )
    ).scalar_one()

    ratio = float(outflow) / float(inflow) if inflow else 0
    signals = []
    risk = 0
    if distinct_senders >= 5:
        risk += 25
        signals.append(f"High fan-in: {distinct_senders} distinct senders in 24h")
    if ratio > 0.7 and outflow > 0:
        risk += 35
        signals.append(f"Pass-through behavior: outflow/inflow ratio {ratio:.2f}")
    if tx.amount and tx.amount >= 10000:
        risk += 15
        signals.append(f"High-value transfer {tx.amount}")
    risk = min(risk, 100)
    return {"risk": risk, "signals": signals}


def detect_social_engineering_patterns(session, tx: Optional[TransactionLog], account_profile: Optional[Dict], recent_events: Optional[List[Dict]]) -> Dict:
    """Lightweight social-engineering checks based on metadata."""
    signals = []
    risk = 0
    if not tx:
        return {"risk": risk, "signals": signals}

    if tx.auth_method and tx.auth_method.upper() in {"OTP_SMS", "OTP"}:
        risk += 10
        signals.append("Weak auth (SMS OTP)")
    if tx.device_fingerprint:
        window_start = tx.tx_datetime - timedelta(hours=12)
        fingerprints = session.execute(
            select(func.count(func.distinct(TransactionLog.device_fingerprint))).where(
                TransactionLog.sender_account_id == tx.sender_account_id,
                TransactionLog.tx_datetime >= window_start,
                TransactionLog.tx_datetime <= tx.tx_datetime,
            )
        ).scalar_one()
        if fingerprints and fingerprints > 1:
            risk += 20
            signals.append("Device change close to transfer")
    if account_profile and account_profile.get("average_amount") and tx.amount:
        avg = account_profile["average_amount"]
        if avg and tx.amount > avg * 3:
            risk += 20
            signals.append("Spike vs normal behavior")
    if recent_events:
        for ev in recent_events:
            if ev.get("type") == "PROFILE_CHANGE":
                risk += 15
                signals.append("Recent profile change before transfer")
                break
    risk = min(risk, 100)
    return {"risk": risk, "signals": signals}


def detect_economic_sabotage_cluster(session) -> List[Dict]:
    """Placeholder batch cluster detection; would run against Neo4j in production."""
    return []


def evaluate_afasa_risk(session, tx_id: Optional[int] = None, tx_ref: Optional[str] = None, account_profile: Optional[Dict] = None, recent_events: Optional[List[Dict]] = None) -> Dict:
    """
    Aggregate AFASA risk signals for a given transaction log entry.
    """
    tx = None
    if tx_id:
        tx = session.get(TransactionLog, tx_id)
    elif tx_ref:
        tx = session.execute(select(TransactionLog).where(TransactionLog.tx_reference == tx_ref)).scalar_one_or_none()

    mule = detect_money_mule_patterns(session, tx)
    social = detect_social_engineering_patterns(session, tx, account_profile or {}, recent_events or [])

    combined_risk = min(100, mule["risk"] * 0.6 + social["risk"] * 0.4)
    suspicion_types = []
    if mule["risk"] >= 40:
        suspicion_types.append("MONEY_MULE")
    if social["risk"] >= 30:
        suspicion_types.append("SOCIAL_ENGINEERING")

    recommended_action = "NO_ACTION"
    if combined_risk >= 70:
        recommended_action = "TEMP_HOLD_AND_VERIFY"
    elif combined_risk >= 40:
        recommended_action = "MONITOR_ONLY"

    return {
        "transaction": tx,
        "overall_risk_score": int(combined_risk),
        "suspicion_types": suspicion_types or ["OTHER"],
        "recommended_action": recommended_action,
        "signals": {
            "money_mule": mule,
            "social_engineering": social,
        },
    }
