import random
from datetime import datetime, timedelta, timezone

from backend.db.session import get_session
from backend.models import Account, Alert, Case, RuleDefinition


def seed_postgres():
    session = get_session()
    try:
        existing_alerts = session.query(Alert).count()
        if existing_alerts > 0:
            print("Postgres already has alerts; skipping alert seed.")
            return

        # Ensure some rules exist
        rule_names = ["R1", "R2", "R3", "R7"]
        rules = {}
        for name in rule_names:
            rule = session.query(RuleDefinition).filter_by(name=name).first()
            if not rule:
                rule = RuleDefinition(name=name, severity=random.choice(["HIGH", "MEDIUM"]))
                session.add(rule)
            rules[name] = rule

        accounts = []
        for idx in range(1, 6):
            acc = Account(account_number=f"ACC-{1000+idx}", customer_name=f"Customer {idx}", risk_score=random.randint(30, 95))
            session.add(acc)
            accounts.append(acc)

        session.flush()

        severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        alerts = []
        for i in range(20):
            created_at = now - timedelta(hours=random.randint(0, 30))
            severity = random.choice(severities)
            rule_choice = random.choice(list(rules.values()))
            alert = Alert(
                rule_id=rule_choice.id,
                subject_account_id=random.choice(accounts).id,
                severity=severity,
                status=random.choice(["OPEN", "IN_PROGRESS", "RESOLVED"]),
                summary=f"Demo alert {i+1} severity {severity}",
                created_at=created_at,
            )
            session.add(alert)
            alerts.append(alert)

        session.flush()

        for alert in alerts[:6]:
            case = Case(
                alert_id=alert.id,
                subject_account_id=alert.subject_account_id,
                status=random.choice(["OPEN", "IN_PROGRESS", "RESOLVED"]),
                created_at=alert.created_at,
            )
            session.add(case)

        session.commit()
        print(f"Seeded {len(alerts)} alerts and {len(accounts)} accounts.")
    finally:
        session.close()


def main():
    seed_postgres()


if __name__ == "__main__":
    main()
