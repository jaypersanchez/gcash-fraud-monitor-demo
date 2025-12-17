import os
from contextlib import contextmanager

from dotenv import load_dotenv
from neo4j import GraphDatabase, READ_ACCESS

load_dotenv()


@contextmanager
def get_driver():
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    if not all([uri, user, password]):
        raise RuntimeError("NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD must be set.")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        yield driver
    finally:
        driver.close()


@contextmanager
def get_read_session():
    """Return a read-only Neo4j session to avoid accidental writes."""
    with get_driver() as driver:
        with driver.session(default_access_mode=READ_ACCESS) as session:
            yield session


def check_connectivity():
    with get_driver() as driver:
        driver.verify_connectivity()
        with driver.session() as session:
            result = session.run("RETURN 1 AS ok").single()
            return {"ok": result["ok"]}
