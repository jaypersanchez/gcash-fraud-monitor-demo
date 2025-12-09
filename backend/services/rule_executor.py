from typing import Optional
from datetime import datetime
from sqlalchemy import select

from backend.db.session import get_session
from backend.models import (
    Alert,
    Case,
    RuleDefinition,
    Account,
    Device,
    TransactionLog,
)
from backend.models.alert import STATUS_VALUES
from backend.services.faf_engine import evaluate_account
from backend.services.feature_builder import build_features_for_account
from backend.afasa.services import evaluate_and_tag_alert
from backend.services.neo4j_client import get_driver


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


def _neo4j_mule_detections(limit: int = 20):
    """
    Pull high-risk accounts from Neo4j (using :Mule nodes) instead of mock data.
    """
    cypher = """
    MATCH (a:Mule)
    RETURN
      a.id   AS accountId,
      coalesce(a.name, a.id) AS customerName,
      1.0    AS riskScore,
      true   AS isFraud
    ORDER BY accountId
    LIMIT $limit
    """
    with get_driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, limit=limit)
            detections = []
            for record in result:
                data = record.data()
                acct = data.get("accountId")
                data["summary"] = f"Mule-like account {acct} detected in Neo4j"
                data["severity"] = "CRITICAL"
                detections.append(data)
            return detections


def _neo4j_identity_detections(limit: int = 10, min_risky: int = 2):
    """
    Detect shared identifiers used by multiple risky accounts.
    """
    cypher = """
    MATCH (id)<-[:HAS_EMAIL|HAS_PHONE|HAS_SSN]-(risky:Mule)
    WITH id, collect(DISTINCT risky) AS riskyAccounts, size(collect(DISTINCT risky)) AS riskyCount
    WHERE riskyCount >= $minRiskyAccounts
    MATCH (id)<-[:HAS_EMAIL|HAS_PHONE|HAS_SSN]-(acc)
    WITH id, riskyCount, collect(DISTINCT acc) AS allAccounts
    RETURN
      CASE
        WHEN id.email IS NOT NULL THEN id.email
        WHEN id.phoneNumber IS NOT NULL THEN id.phoneNumber
        ELSE id.ssn
      END AS deviceId,
      head(allAccounts) AS anchor,
      riskyCount AS riskyAccounts,
      size(allAccounts) AS totalAccounts
    ORDER BY riskyAccounts DESC, totalAccounts DESC
    LIMIT $limit
    """
    with get_driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                minRiskyAccounts=min_risky,
                limit=limit,
            )
            detections = []
            for record in result:
                anchor = record["anchor"] or {}
                detections.append(
                    {
                        "subject_account_number": anchor.get("account_number") or anchor.get("id"),
                        "subject_customer_name": anchor.get("customer_name") or anchor.get("name") or anchor.get("id"),
                        "severity": "HIGH",
                        "summary": f"Shared identifier {record['deviceId']} used by {record['totalAccounts']} accounts",
                        "linked_devices": [{"device_id": record["deviceId"], "device_type": "Identifier"}],
                        "details": {
                            "pattern": "shared_identifier",
                            "risky_accounts": record["riskyAccounts"],
                            "total_accounts": record["totalAccounts"],
                        },
                    }
                )
            return detections


def _ensure_transaction_log(session, detection: dict) -> TransactionLog:
    """
    Create a TransactionLog entry for detections that provide tx metadata.
    This keeps the demo aligned with BSP logging expectations.
    """
    tx_ref = detection.get("tx_ref") or detection.get("tx_reference")
    if not tx_ref:
        return None
    tx = session.execute(select(TransactionLog).where(TransactionLog.tx_reference == tx_ref)).scalar_one_or_none()
    if tx:
        return tx
    tx = TransactionLog(
        tx_reference=tx_ref,
        sender_account_id=detection.get("subject_account_number") or "UNKNOWN",
        receiver_account_id=detection.get("linked_accounts", [{}])[0].get("account_number") if detection.get("linked_accounts") else "UNKNOWN",
        amount=detection.get("amount") or 0,
        currency=detection.get("currency") or "PHP",
        tx_datetime=detection.get("tx_datetime") or datetime.utcnow(),
        ofi=detection.get("ofi"),
        rfi=detection.get("rfi"),
        channel=detection.get("channel") or "MOBILE_APP",
        auth_method=detection.get("auth_method") or "OTP_SMS",
        device_fingerprint=detection.get("device_id"),
        ip_address=detection.get("ip_address"),
        browser_user_agent=detection.get("browser_user_agent"),
        non_financial_action=detection.get("non_financial_action"),
        network_reference=detection.get("network_reference"),
    )
    session.add(tx)
    session.flush()
    return tx


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
            detections = []
            rule_name = (rule.name or "").lower()
            if "mule" in rule_name:
                detections = _neo4j_mule_detections(limit=20)
            elif "identity" in rule_name:
                detections = _neo4j_identity_detections(limit=20)
            else:
                continue

            for detection in detections:
                account_number = detection.get("subject_account_number") or detection.get("accountId")
                customer_name = detection.get("subject_customer_name") or detection.get("customerName") or "Unknown"
                subject_account = _get_or_create_account(
                    session,
                    account_number,
                    customer_name,
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
                tx_log = _ensure_transaction_log(session, detection)
                evaluate_and_tag_alert(session, alert, tx_ref=detection.get("tx_ref"), tx_id=tx_log.id if tx_log else None)
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
                evaluate_and_tag_alert(session, alert, tx_ref=cand.anchor_id if cand.anchor_type == "TRANSACTION" else None)
                generated += 1
        session.commit()
        return generated
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
