from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from backend.afasa.constants import (
    REASON_CATEGORIES,
    SUSPICION_TYPES,
    DISPUTE_STATUS,
    VERIFICATION_EVENT_TYPES,
)
from backend.afasa.models import AfasaDisputedTransaction, AfasaVerificationEvent
from backend.afasa.rules import evaluate_afasa_risk
from backend.afasa.schemas import disputed_transaction_to_dict
from backend.models.transaction import TransactionLog


AFASA_HOLD_WINDOW_DAYS = 30
AFASA_RISK_THRESHOLD = 60


def initiate_disputed_transaction(session, alert_id: int, tx_id: Optional[int], reason_category: str, suspicion_type: str, initiated_by: str):
    if reason_category not in REASON_CATEGORIES:
        raise ValueError("Invalid reason_category")
    if suspicion_type not in SUSPICION_TYPES:
        raise ValueError("Invalid suspicion_type")
    tx = session.get(TransactionLog, tx_id) if tx_id else None
    dispute = AfasaDisputedTransaction(
        alert_id=alert_id,
        original_tx_id=tx_id,
        source_account_id=tx.sender_account_id if tx else "",
        beneficiary_account_id=tx.receiver_account_id if tx else "",
        amount=tx.amount if tx else None,
        currency=tx.currency if tx else None,
        reason_category=reason_category,
        suspicion_type=suspicion_type,
        status="PENDING_HOLD",
        max_hold_until=(datetime.utcnow() + timedelta(days=AFASA_HOLD_WINDOW_DAYS)),
    )
    session.add(dispute)
    session.flush()
    event = AfasaVerificationEvent(
        disputed_tx_id=dispute.id,
        event_type="INITIATED",
        notes="Dispute created",
        created_by=initiated_by,
    )
    session.add(event)
    session.commit()
    return dispute


def apply_temporary_hold(session, disputed_tx_id: int, actor: str):
    dispute = session.get(AfasaDisputedTransaction, disputed_tx_id)
    if not dispute:
        raise ValueError("Disputed transaction not found")
    dispute.start_hold(hold_window_days=AFASA_HOLD_WINDOW_DAYS)
    evt = AfasaVerificationEvent(
        disputed_tx_id=dispute.id,
        event_type="CUSTOMER_CONTACTED",
        notes="Temporary hold applied; verification initiated",
        created_by=actor,
    )
    session.add(evt)
    session.commit()
    return dispute


def release_or_restitute_funds(session, disputed_tx_id: int, decision: str, actor: str, notes: Optional[str] = None):
    dispute = session.get(AfasaDisputedTransaction, disputed_tx_id)
    if not dispute:
        raise ValueError("Disputed transaction not found")
    if decision.upper() == "RELEASE":
        dispute.status = "RELEASED"
        evt_type = "FUNDS_RELEASED"
    elif decision.upper() == "RESTITUTION":
        dispute.status = "WRITTEN_OFF"
        evt_type = "FUNDS_RESTITUTED"
    else:
        dispute.status = "ESCALATED"
        evt_type = "ESCALATED_TO_LEA"
    dispute.hold_end_at = datetime.utcnow()
    evt = AfasaVerificationEvent(
        disputed_tx_id=dispute.id,
        event_type=evt_type,
        notes=notes or f"Decision: {decision}",
        created_by=actor,
    )
    session.add(evt)
    session.commit()
    return dispute


def add_verification_event(session, disputed_tx_id: int, event_type: str, notes: Optional[str], actor: str):
    if event_type not in VERIFICATION_EVENT_TYPES:
        raise ValueError("Invalid event type")
    dispute = session.get(AfasaDisputedTransaction, disputed_tx_id)
    if not dispute:
        raise ValueError("Disputed transaction not found")
    evt = AfasaVerificationEvent(
        disputed_tx_id=dispute.id,
        event_type=event_type,
        notes=notes,
        created_by=actor,
    )
    session.add(evt)
    session.commit()
    return evt


def auto_enforce_max_hold_period(session):
    now = datetime.utcnow()
    to_release = session.execute(
        select(AfasaDisputedTransaction).where(
            AfasaDisputedTransaction.status == "HELD",
            AfasaDisputedTransaction.max_hold_until != None,  # noqa: E711
            AfasaDisputedTransaction.max_hold_until < now,
        )
    ).scalars()
    count = 0
    for dispute in to_release:
        dispute.status = "ESCALATED"
        dispute.hold_end_at = now
        evt = AfasaVerificationEvent(
            disputed_tx_id=dispute.id,
            event_type="ESCALATED_TO_LEA",
            notes="Max hold reached; escalate or release required",
            created_by="afasa_auto_enforcer",
        )
        session.add(evt)
        count += 1
    session.commit()
    return count


def evaluate_and_tag_alert(session, alert, tx_ref: Optional[str] = None, tx_id: Optional[int] = None):
    """
    Evaluate AFASA risk and tag the alert/case accordingly.
    """
    result = evaluate_afasa_risk(session, tx_id=tx_id, tx_ref=tx_ref)
    if not result:
        return None
    risk = result.get("overall_risk_score") or 0
    if risk >= AFASA_RISK_THRESHOLD:
        alert.is_afasa = True
        alert.afasa_suspicion_type = ",".join(result.get("suspicion_types") or [])
        alert.afasa_risk_score = risk
        session.add(alert)
        session.flush()
    return result
