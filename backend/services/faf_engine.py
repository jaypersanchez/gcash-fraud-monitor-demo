from dataclasses import dataclass
from typing import Callable, List, Dict, Any


@dataclass
class FAFRule:
    id: str
    name: str
    category: str
    severity: str
    enabled: bool
    condition: Callable[[Dict[str, Any]], bool]
    anchor_type: str = "account"


@dataclass
class AlertCandidate:
    rule_id: str
    severity: str
    title: str
    summary: str
    anchor_type: str
    anchor_id: str


def _load_faf_rules() -> List[FAFRule]:
    """
    MVP rule registry (hardcoded). Later: load from config/DB.
    """
    rules: List[FAFRule] = []

    # High centrality mule node
    rules.append(
        FAFRule(
            id="FAF-GRAPH-001",
            name="High centrality mule node",
            category="GRAPH",
            severity="HIGH",
            enabled=True,
            anchor_type="account",
            condition=lambda f: f.get("graph_centrality", 0) >= 0.8,
        )
    )

    # Fan-out to many new recipients (24h)
    rules.append(
        FAFRule(
            id="FAF-P2P-003",
            name="Fan-out to many new recipients",
            category="P2P",
            severity="HIGH",
            enabled=True,
            anchor_type="account",
            condition=lambda f: f.get("num_new_recipients_24h", 0) >= 5,
        )
    )

    # Impossible travel – login
    rules.append(
        FAFRule(
            id="FAF-LOGIN-001",
            name="Impossible Travel – Login",
            category="LOGIN",
            severity="HIGH",
            enabled=True,
            anchor_type="account",
            condition=lambda f: f.get("impossible_travel_flag", False) is True,
        )
    )

    return rules


_FAF_RULES: List[FAFRule] = _load_faf_rules()


def evaluate_account(account_id: str, features: Dict[str, Any]) -> List[AlertCandidate]:
    """
    Evaluate all FAF rules for this account and return a list of alert candidates.
    """
    alerts: List[AlertCandidate] = []
    for rule in _FAF_RULES:
        if not rule.enabled:
            continue
        try:
            if rule.condition(features):
                summary = f"Account {account_id} triggered FAF rule {rule.id} ({rule.name})."
                alerts.append(
                    AlertCandidate(
                        rule_id=rule.id,
                        severity=rule.severity,
                        title=rule.name,
                        summary=summary,
                        anchor_type=rule.anchor_type,
                        anchor_id=account_id,
                    )
                )
        except Exception:
            # Fail-safe: skip rule if it errors
            continue
    return alerts
