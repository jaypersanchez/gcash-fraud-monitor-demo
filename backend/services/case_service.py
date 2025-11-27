from typing import Optional
from sqlalchemy import select

from backend.db.session import get_session
from backend.models import Case, CaseAction
from backend.models.case_action import ACTION_VALUES
from backend.models.alert import STATUS_VALUES


STATUS_FOR_ACTION = {
    "BLOCK_ACCOUNT": "RESOLVED",
    "MARK_SAFE": "RESOLVED",
    "ESCALATE": "IN_PROGRESS",
}


def add_case_action(case_id: int, action: str, performed_by: Optional[str] = None, notes: Optional[str] = None):
    if action not in ACTION_VALUES:
        raise ValueError(f"Invalid action: {action}")

    session = get_session()
    try:
        case = session.execute(select(Case).where(Case.id == case_id)).scalar_one_or_none()
        if not case:
            return None

        case.status = STATUS_FOR_ACTION.get(action, case.status)

        case_action = CaseAction(
            case_id=case_id,
            action=action,
            performed_by=performed_by or "fraud_analyst_1",
            notes=notes,
        )
        session.add(case_action)
        session.add(case)
        session.commit()
        session.refresh(case)
        return case
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_actions(case_id: int):
    session = get_session()
    try:
        actions = session.execute(
            select(CaseAction).where(CaseAction.case_id == case_id).order_by(CaseAction.created_at.asc())
        ).scalars().all()
        return actions
    finally:
        session.close()
