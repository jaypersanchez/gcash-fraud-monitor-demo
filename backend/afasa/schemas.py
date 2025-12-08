from datetime import datetime
from typing import Any, Dict, Optional


def _ts(val: Optional[datetime]) -> Optional[str]:
    return val.isoformat() if val else None


def disputed_transaction_to_dict(model) -> Dict[str, Any]:
    if model is None:
        return {}
    return {
        "id": model.id,
        "alert_id": model.alert_id,
        "original_tx_id": model.original_tx_id,
        "source_account_id": model.source_account_id,
        "beneficiary_account_id": model.beneficiary_account_id,
        "amount": float(model.amount) if model.amount is not None else None,
        "currency": model.currency,
        "reason_category": model.reason_category,
        "suspicion_type": model.suspicion_type,
        "status": model.status,
        "hold_start_at": _ts(model.hold_start_at),
        "hold_end_at": _ts(model.hold_end_at),
        "max_hold_until": _ts(model.max_hold_until),
        "created_at": _ts(model.created_at),
        "updated_at": _ts(model.updated_at),
        "verification_events": [verification_event_to_dict(evt) for evt in getattr(model, "verification_events", [])],
    }


def verification_event_to_dict(model) -> Dict[str, Any]:
    if model is None:
        return {}
    return {
        "id": model.id,
        "disputed_tx_id": model.disputed_tx_id,
        "event_type": model.event_type,
        "notes": model.notes,
        "created_by": model.created_by,
        "created_at": _ts(model.created_at),
    }


def afasa_risk_summary(alert_id: int, suspicion_type: Optional[str], risk_score: Optional[int], recommended_action: str) -> Dict[str, Any]:
    return {
        "alert_id": alert_id,
        "suspicion_type": suspicion_type,
        "risk_score": risk_score,
        "recommended_action": recommended_action,
    }
