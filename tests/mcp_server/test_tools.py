# tests/mcp_server/test_tools.py — Tool handler tests (mocked, no Neo4j)
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


class TestListAvailableTool:
    """Test list_available tool handler error and success paths."""

    def test_connection_error_returns_structured_error(self):
        """get_connection() failure → JSON error with Neo4j message."""
        with patch(
            "mcp_server.tools.get_connection",
            side_effect=RuntimeError("Connection refused"),
        ):
            from mcp_server.tools import list_available

            result = json.loads(list_available())
            assert "error" in result
            assert "Neo4j error" in result["error"]
            assert "Connection refused" in result["error"]

    def test_query_error_returns_structured_error(self):
        """persistence_list_available() failure → JSON error."""
        mock_conn = MagicMock()
        with (
            patch("mcp_server.tools.get_connection", return_value=mock_conn),
            patch(
                "mcp_server.tools.persistence_list_available",
                side_effect=RuntimeError("Query timed out"),
            ),
        ):
            from mcp_server.tools import list_available

            result = json.loads(list_available())
            assert "error" in result
            assert "Query timed out" in result["error"]

    def test_success_returns_recipes_and_formats(self):
        """Happy path → JSON with recipes and formats keys."""
        mock_conn = MagicMock()
        mock_result = {
            "recipes": [{"recipe_id": "payroll_v1", "name": "Payroll", "rule_count": 2}],
            "formats": [],
        }
        with (
            patch("mcp_server.tools.get_connection", return_value=mock_conn),
            patch(
                "mcp_server.tools.persistence_list_available",
                return_value=mock_result,
            ),
        ):
            from mcp_server.tools import list_available

            result = json.loads(list_available())
            assert result["recipes"] == mock_result["recipes"]
            assert result["formats"] == []
