from typing import Dict, Any

from sqlalchemy.orm import Session
from neo4j import Driver


def build_features_for_account(
    account_id: str,
    db_session: Session,
    neo4j_driver: Driver,
) -> Dict[str, Any]:
    """
    Build a normalized feature dictionary for the given account_id
    using Postgres (SQLAlchemy) and Neo4j context.

    Expected keys (MVP defaults provided):
    - graph_centrality: float
    - num_new_recipients_24h: int
    - impossible_travel_flag: bool
    """
    features: Dict[str, Any] = {"account_id": account_id}

    # --- TODO: Enrich from Postgres models (Account, Alert, etc.) ---
    # Example:
    # from backend.models import Account
    # acct = db_session.query(Account).filter_by(account_number=account_id).one_or_none()
    # if acct:
    #     features["is_high_risk_account"] = getattr(acct, "is_high_risk", False)

    # --- TODO: Enrich from Neo4j graph metrics ---
    # Example centrality fetch:
    # with neo4j_driver.session() as session:
    #     record = session.run(
    #         "MATCH (a) WHERE a.account_number = $account_id RETURN a.centrality AS c",
    #         account_id=account_id,
    #     ).single()
    #     if record and record["c"] is not None:
    #         features["graph_centrality"] = float(record["c"])

    # Set safe defaults to avoid KeyErrors in FAF rules
    features.setdefault("graph_centrality", 0.0)
    features.setdefault("num_new_recipients_24h", 0)
    features.setdefault("impossible_travel_flag", False)

    return features
