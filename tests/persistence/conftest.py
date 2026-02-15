# tests/persistence/conftest.py — Neo4j fixtures for integration tests
import os

import pytest


def _neo4j_available() -> bool:
    return bool(os.environ.get("NEO4J_URI") and os.environ.get("NEO4J_PASSWORD"))


# Skip integration tests unless Neo4j credentials are set
requires_neo4j = pytest.mark.skipif(
    not _neo4j_available(),
    reason="NEO4J_URI and NEO4J_PASSWORD env vars required",
)


@pytest.fixture
def neo4j_conn():
    """Provide a Neo4jConnection for integration tests, cleaned up after use."""
    if not _neo4j_available():
        pytest.skip("NEO4J_URI and NEO4J_PASSWORD env vars required")

    from persistence.connection import Neo4jConnection

    conn = Neo4jConnection()
    yield conn
    conn.close()
