from datetime import datetime

from backend.db.session import get_session
from backend.models import RuleDefinition, Account, Alert, TransactionLog


def _bootstrap_alert():
    session = get_session()
    try:
        rule = RuleDefinition(name="FAF-AFASA", description="afasa test", severity="HIGH", enabled=True)
        acct = Account(account_number="GCASH-TEST-1", customer_name="Test User")
        session.add_all([rule, acct])
        session.flush()
        alert = Alert(rule_id=rule.id, subject_account_id=acct.id, severity="HIGH", summary="test", details={})
        session.add(alert)
        session.flush()
        tx = TransactionLog(
            tx_reference="TX-UNIT-1",
            sender_account_id="GCASH-TEST-1",
            receiver_account_id="GCASH-TEST-2",
            amount=1000,
            currency="PHP",
            tx_datetime=datetime.utcnow(),
            channel="MOBILE_APP",
            auth_method="OTP_SMS",
        )
        session.add(tx)
        session.commit()
        return alert.id, tx.id
    finally:
        session.close()


def test_afasa_dispute_lifecycle(client):
    alert_id, tx_id = _bootstrap_alert()

    # create dispute
    resp = client.post(
        "/api/afasa/disputes",
        json={
            "alert_id": alert_id,
            "tx_id": tx_id,
            "reason_category": "FMS_DETECTED",
            "suspicion_type": "MONEY_MULE",
            "initiated_by": "test",
        },
    )
    assert resp.status_code == 201
    dispute = resp.get_json()
    assert dispute["status"] == "PENDING_HOLD"

    # apply hold
    resp_hold = client.post(f"/api/afasa/disputes/{dispute['id']}/hold", json={"actor": "tester"})
    assert resp_hold.status_code == 200
    held = resp_hold.get_json()
    assert held["status"] == "HELD"

    # add verification event
    resp_evt = client.post(
        f"/api/afasa/disputes/{dispute['id']}/events",
        json={"event_type": "CUSTOMER_CONTACTED", "notes": "called", "actor": "tester"},
    )
    assert resp_evt.status_code == 201

    # release
    resp_rel = client.post(
        f"/api/afasa/disputes/{dispute['id']}/release", json={"decision": "RELEASE", "actor": "tester"}
    )
    assert resp_rel.status_code == 200
    assert resp_rel.get_json()["status"] == "RELEASED"
