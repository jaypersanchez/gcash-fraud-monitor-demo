from typing import Optional
from sqlalchemy import select

from backend.db.session import get_session
from backend.models import (
    Alert,
    Case,
    RuleDefinition,
    Account,
    Device,
)
from backend.models.alert import STATUS_VALUES
from . import neo4j_client_mock
from backend.services.faf_engine import evaluate_account
from backend.services.feature_builder import build_features_for_account


def _get_or_create_account(session, account_number: str, customer_name: str):
    account = session.execute(
        select(Account).where(Account.account_number == account_number)
    ).scalar_one_or_none()
    if account:
        return account
    account = Account(account_number=account_number, customer_name=customer_name)
    session.add(account)
    session.flush()
    return account


def _get_or_create_device(session, device_id: str, device_type: Optional[str] = None):
    device = session.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
    if device:
        return device
    device = Device(device_id=device_id, device_type=device_type)
    session.add(device)
    session.flush()
    return device


def _get_or_create_rule_by_key(session, rule_key: str, severity: str, description: str = None) -> RuleDefinition:
    rule = session.execute(select(RuleDefinition).where(RuleDefinition.name == rule_key)).scalar_one_or_none()
    if rule:
        return rule
    rule = RuleDefinition(
        name=rule_key,
        description=description or rule_key,
        severity=severity or "HIGH",
        enabled=True,
    )
    session.add(rule)
    session.flush()
    return rule


def refresh_alerts(rule_id: Optional[int] = None, neo4j_driver=None) -> int:
    session = get_session()
    try:
        query = select(RuleDefinition).where(RuleDefinition.enabled.is_(True))
        if rule_id:
            query = query.where(RuleDefinition.id == rule_id)
        rules = session.execute(query).scalars().all()
        generated = 0
        faf_accounts = set()

        for rule in rules:
            detections = neo4j_client_mock.run_rule(rule)
            for detection in detections:
                subject_account = _get_or_create_account(
                    session,
                    detection.get("subject_account_number"),
                    detection.get("subject_customer_name", "Unknown"),
                )

                linked_devices_data = detection.get("linked_devices", [])
                for device_info in linked_devices_data:
                    _get_or_create_device(session, device_info.get("device_id"), device_info.get("device_type"))

                alert = Alert(
                    rule_id=rule.id,
                    subject_account_id=subject_account.id,
                    severity=detection.get("severity", rule.severity or "MEDIUM"),
                    status=STATUS_VALUES[0],
                    summary=detection.get("summary", "Suspicious activity detected"),
                    details=detection.get("details", detection),
                )
                session.add(alert)
                session.flush()

                case = Case(
                    alert_id=alert.id,
                    subject_account_id=subject_account.id,
                    status=STATUS_VALUES[0],
                    network_summary=detection.get("network_summary"),
                    linked_accounts=detection.get("linked_accounts", []),
                    linked_devices=linked_devices_data,
                )
                session.add(case)
                generated += 1

                if subject_account.account_number:
                    faf_accounts.add(subject_account.account_number)

        # FAF evaluation for gathered accounts (MVP: per account_number)
        for acct_number in faf_accounts:
            features = build_features_for_account(acct_number, session, neo4j_driver)
            candidates = evaluate_account(acct_number, features)
            if not candidates:
                continue
            subject_account = _get_or_create_account(session, acct_number, "Unknown")
            for cand in candidates:
                faf_rule = _get_or_create_rule_by_key(session, cand.rule_id, cand.severity, cand.title)
                alert = Alert(
                    rule_id=faf_rule.id,
                    subject_account_id=subject_account.id,
                    severity=cand.severity if cand.severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW") else "HIGH",
                    status=STATUS_VALUES[0],
                    summary=cand.summary,
                    details={
                        "anchor_type": cand.anchor_type,
                        "anchor_id": cand.anchor_id,
                        "faf": True,
                    },
                )
                session.add(alert)
                session.flush()
                case = Case(
                    alert_id=alert.id,
                    subject_account_id=subject_account.id,
                    status=STATUS_VALUES[0],
                    network_summary=None,
                    linked_accounts=[],
                    linked_devices=[],
                )
                session.add(case)
                generated += 1
        session.commit()
        return generated
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
