# persistence/connection.py — Neo4j driver wrapper (only file importing neo4j)
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase


class Neo4jConnection:
    """Thin wrapper around the Neo4j Python driver.

    Matches the established pattern from docs/environment_and_best_practices.md.
    Env vars: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.uri = uri or os.environ["NEO4J_URI"]
        self.user = user or os.environ.get("NEO4J_USER", "neo4j")
        self.password = password or os.environ["NEO4J_PASSWORD"]
        self.driver = GraphDatabase.driver(
            self.uri, auth=(self.user, self.password)
        )

    def __enter__(self) -> Neo4jConnection:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        self.driver.close()

    def verify_connection(self) -> bool:
        """Run a trivial query to check the connection is alive."""
        with self.driver.session() as session:
            result = session.run("RETURN 1 AS test")
            record = result.single()
            return record["test"] == 1

    def run_query(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a read query and return results as a list of dicts."""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def run_write(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, int]:
        """Execute a write query and return mutation counters."""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            summary = result.consume()
            return {
                "nodes_created": summary.counters.nodes_created,
                "relationships_created": summary.counters.relationships_created,
                "properties_set": summary.counters.properties_set,
            }
