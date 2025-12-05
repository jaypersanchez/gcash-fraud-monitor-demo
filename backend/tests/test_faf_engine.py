from backend.services.faf_engine import evaluate_account


def test_faf_engine_triggers_rules():
    account_id = "acct-123"
    features = {
        "graph_centrality": 0.9,
        "num_new_recipients_24h": 6,
        "impossible_travel_flag": True,
    }
    alerts = evaluate_account(account_id, features)
    rule_ids = {a.rule_id for a in alerts}
    assert "FAF-GRAPH-001" in rule_ids
    assert "FAF-P2P-003" in rule_ids
    assert "FAF-LOGIN-001" in rule_ids
