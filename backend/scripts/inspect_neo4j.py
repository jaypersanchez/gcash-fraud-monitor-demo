"""
Inspect Neo4j schema/data for the current environment.

Uses env vars:
  NEO4J_URI
  NEO4J_USER (or NEO4J_USERNAME)
  NEO4J_PASSWORD

Usage:
  python backend/scripts/inspect_neo4j.py
"""
import os
from typing import List
from dotenv import load_dotenv
from neo4j import GraphDatabase

def get_env():
    load_dotenv()
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")
    if not all([uri, user, password]):
        raise SystemExit("NEO4J_URI, NEO4J_USER/NEO4J_USERNAME, NEO4J_PASSWORD are required")
    return uri, user, password

def run_query(session, query: str, **params):
    return list(session.run(query, **params))

def get_labels(session) -> List[str]:
    try:
        rows = run_query(session, "CALL db.labels() YIELD label RETURN label")
        return [r["label"] for r in rows]
    except Exception:
        rows = run_query(session, "SHOW LABELS YIELD name RETURN name")
        return [r["name"] for r in rows]

def get_rel_types(session) -> List[str]:
    try:
        rows = run_query(session, "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
        return [r["relationshipType"] for r in rows]
    except Exception:
        rows = run_query(session, "SHOW RELATIONSHIP TYPES YIELD name RETURN name")
        return [r["name"] for r in rows]

def sample_nodes(session, label: str, limit: int = 3):
    rows = run_query(session, f"MATCH (n:`{label}`) RETURN n LIMIT $limit", limit=limit)
    return [r["n"] for r in rows]

def count_label(session, label: str) -> int:
    rows = run_query(session, f"MATCH (n:`{label}`) RETURN count(n) AS c")
    return rows[0]["c"] if rows else 0

def count_rel_type(session, rel_type: str) -> int:
    rows = run_query(session, f"MATCH ()-[r:`{rel_type}`]->() RETURN count(r) AS c")
    return rows[0]["c"] if rows else 0

def main():
    uri, user, password = get_env()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        labels = get_labels(session)
        rels = get_rel_types(session)
        print("Labels:")
        for lbl in labels:
            cnt = count_label(session, lbl)
            print(f"  - {lbl}: {cnt}")
            for node in sample_nodes(session, lbl, limit=2):
                print(f"    sample: {dict(node)}")

        print("\nRelationship types:")
        for rel in rels:
            cnt = count_rel_type(session, rel)
            print(f"  - {rel}: {cnt}")

        if "Account" in labels and "Device" in labels:
            rows = run_query(session, "MATCH (a:Account)-[:USES]->(d:Device) RETURN count(*) AS c")
            print(f"\nAccount-USES-Device count: {rows[0]['c'] if rows else 0}")
        if "Account" in labels and "Transaction" in labels:
            rows = run_query(session, "MATCH (a:Account)-[:PERFORMS]->(t:Transaction)-[:TO]->(b:Account) RETURN count(*) AS c")
            print(f"Account->Transaction->Account count: {rows[0]['c'] if rows else 0}")

    driver.close()

if __name__ == "__main__":
    main()
