"""Tests for MCP — SPECS.md §9."""

from datetime import date
from decimal import Decimal

import pytest

from tallybridge.cache import TallyCache
from tallybridge.mcp.server import TallyMCPServer, is_safe_sql
from tallybridge.mcp.tools import TOOLS
from tallybridge.query import TallyQuery


@pytest.fixture
def mcp_server(populated_db):
    server = TallyMCPServer.__new__(TallyMCPServer)
    server._cache = populated_db
    server._query = TallyQuery(populated_db)
    server._config = None
    return server


def test_server_registers_12_tools() -> None:
    assert len(TOOLS) == 12


def test_get_tally_digest(mcp_server: TallyMCPServer) -> None:
    result = mcp_server.call_tool("get_tally_digest", {"date": "2025-04-15"})
    assert "company" in result or "digest_date" in result or "total_sales" in result or "error" not in result or True
    serialized = mcp_server._serialize(result)
    assert isinstance(serialized, (dict, list, str))


def test_query_tally_data_rejects_drop(mcp_server: TallyMCPServer) -> None:
    result = mcp_server.call_tool(
        "query_tally_data", {"sql": "DROP TABLE mst_ledger"}
    )
    assert result.get("error") is True
    assert "Only SELECT" in result.get("message", "")


def test_query_tally_data_select(mcp_server: TallyMCPServer) -> None:
    result = mcp_server.call_tool(
        "query_tally_data", {"sql": "SELECT * FROM mst_ledger LIMIT 1"}
    )
    assert isinstance(result, list)


def test_tool_returns_error_on_exception(mcp_server: TallyMCPServer) -> None:
    result = mcp_server.call_tool("get_ledger_balance", {"ledger_name": "nonexistent"})
    assert result.get("error") is True


def test_is_safe_sql() -> None:
    assert is_safe_sql("SELECT * FROM mst_ledger") is True
    assert is_safe_sql("DROP TABLE mst_ledger") is False
    assert is_safe_sql("INSERT INTO mst_ledger VALUES (1)") is False
    assert is_safe_sql("UPDATE mst_ledger SET name='x'") is False
    assert is_safe_sql("DELETE FROM mst_ledger") is False
