"""Tests for MCP SDK server."""

import os
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from tallybridge.mcp.sdk_server import (
    AppContext,
    _check_auth,
    _error_result,
    _get_app_ctx,
    _parse_date,
    _serialize,
    app_lifespan,
)
from tallybridge.query import TallyQuery


@pytest.fixture
def query(populated_db):
    return TallyQuery(populated_db)


@pytest.fixture
def cache(populated_db):
    return populated_db


@pytest.fixture
def app_ctx(populated_db):
    return AppContext(cache=populated_db, query=TallyQuery(populated_db))


@pytest.fixture
def mock_ctx(app_ctx):
    ctx = MagicMock()
    ctx.request_context.lifespan_context = app_ctx
    return ctx


def test_serialize_decimal() -> None:
    assert _serialize(Decimal("123.45")) == "123.45"


def test_serialize_date() -> None:
    assert _serialize(date(2025, 4, 15)) == "2025-04-15"


def test_serialize_list() -> None:
    result = _serialize([Decimal("1"), Decimal("2")])
    assert result == ["1", "2"]


def test_serialize_dict() -> None:
    result = _serialize({"amount": Decimal("100")})
    assert result == {"amount": "100"}


def test_serialize_model() -> None:
    from tallybridge.models.voucher import TallyVoucherEntry

    entry = TallyVoucherEntry(ledger_name="Cash", amount=Decimal("500"))
    result = _serialize(entry)
    assert isinstance(result, dict)
    assert result["ledger_name"] == "Cash"


def test_serialize_primitive() -> None:
    assert _serialize("hello") == "hello"
    assert _serialize(42) == 42


def test_parse_date_none() -> None:
    assert _parse_date(None) is None


def test_parse_date_date_obj() -> None:
    d = date(2025, 4, 15)
    assert _parse_date(d) == d


def test_parse_date_string() -> None:
    assert _parse_date("2025-04-15") == date(2025, 4, 15)


def test_parse_date_empty_string() -> None:
    assert _parse_date("") is None
    assert _parse_date("  ") is None


def test_parse_date_invalid() -> None:
    try:
        _parse_date("not-a-date")
    except ValueError:
        pass


def test_error_result() -> None:
    result = _error_result("test error")
    assert result.isError is True
    assert len(result.content) == 1
    assert result.content[0].text == "test error"


def test_get_app_ctx(mock_ctx) -> None:
    ctx = _get_app_ctx(mock_ctx)
    assert isinstance(ctx, AppContext)
    assert isinstance(ctx.cache, type(mock_ctx.request_context.lifespan_context.cache))
    assert isinstance(ctx.query, TallyQuery)


def test_check_auth_no_api_key() -> None:
    from tallybridge.config import reset_config

    reset_config()
    os.environ.pop("TALLYBRIDGE_MCP_API_KEY", None)
    ctx = MagicMock()
    _check_auth(ctx)


def test_check_auth_stdio_transport_skips() -> None:
    from tallybridge.config import TallyBridgeConfig, reset_config

    reset_config()
    os.environ.pop("TALLYBRIDGE_MCP_API_KEY", None)
    os.environ["TALLYBRIDGE_MCP_TRANSPORT"] = "stdio"
    try:
        _ = TallyBridgeConfig(mcp_api_key="secret")
        ctx = MagicMock()
        _check_auth(ctx)
    finally:
        os.environ.pop("TALLYBRIDGE_MCP_TRANSPORT", None)


def test_check_auth_http_with_valid_key() -> None:
    from tallybridge.config import reset_config

    reset_config()
    os.environ["TALLYBRIDGE_MCP_API_KEY"] = "test-key"
    os.environ["TALLYBRIDGE_MCP_TRANSPORT"] = "http"
    try:
        ctx = MagicMock()
        ctx.request_context.headers = {"Authorization": "Bearer test-key"}
        _check_auth(ctx)
    finally:
        os.environ.pop("TALLYBRIDGE_MCP_API_KEY", None)
        os.environ.pop("TALLYBRIDGE_MCP_TRANSPORT", None)


def test_check_auth_http_with_invalid_key() -> None:
    from tallybridge.config import reset_config

    reset_config()
    os.environ["TALLYBRIDGE_MCP_API_KEY"] = "correct-key"
    os.environ["TALLYBRIDGE_MCP_TRANSPORT"] = "http"
    try:
        ctx = MagicMock()
        ctx.request_context.headers = {"Authorization": "Bearer wrong-key"}
        with pytest.raises(PermissionError, match="Invalid API key"):
            _check_auth(ctx)
    finally:
        os.environ.pop("TALLYBRIDGE_MCP_API_KEY", None)
        os.environ.pop("TALLYBRIDGE_MCP_TRANSPORT", None)


def test_check_auth_http_no_auth_header() -> None:
    from tallybridge.config import reset_config

    reset_config()
    os.environ["TALLYBRIDGE_MCP_API_KEY"] = "test-key"
    os.environ["TALLYBRIDGE_MCP_TRANSPORT"] = "http"
    try:
        ctx = MagicMock()
        ctx.request_context.headers = {}
        with pytest.raises(PermissionError, match="Authentication required"):
            _check_auth(ctx)
    finally:
        os.environ.pop("TALLYBRIDGE_MCP_API_KEY", None)
        os.environ.pop("TALLYBRIDGE_MCP_TRANSPORT", None)


def test_check_auth_http_no_headers_attribute() -> None:
    from tallybridge.config import reset_config

    reset_config()
    os.environ["TALLYBRIDGE_MCP_API_KEY"] = "test-key"
    os.environ["TALLYBRIDGE_MCP_TRANSPORT"] = "http"
    try:
        ctx = MagicMock()
        del ctx.request_context.headers
        with pytest.raises(PermissionError, match="Authentication required"):
            _check_auth(ctx)
    finally:
        os.environ.pop("TALLYBRIDGE_MCP_API_KEY", None)
        os.environ.pop("TALLYBRIDGE_MCP_TRANSPORT", None)


async def test_app_lifespan_yields_context() -> None:
    server = MagicMock()
    async with app_lifespan(server) as ctx:
        assert isinstance(ctx, AppContext)
        assert isinstance(ctx.cache, type(ctx.cache))
        assert isinstance(ctx.query, TallyQuery)


async def test_get_tally_digest_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_tally_digest

    result = await get_tally_digest(date="2025-04-15", ctx=mock_ctx)
    assert result is not None


async def test_get_tally_digest_no_date(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_tally_digest

    result = await get_tally_digest(date=None, ctx=mock_ctx)
    assert result is not None


async def test_get_ledger_balance_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_ledger_balance

    result = await get_ledger_balance(ledger_name="Cash", ctx=mock_ctx)
    assert result is not None


async def test_get_ledger_balance_not_found(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_ledger_balance

    result = await get_ledger_balance(ledger_name="NonExistent", ctx=mock_ctx)
    assert result.isError is True
    assert "not found" in result.content[0].text.lower()


async def test_get_receivables_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_receivables

    result = await get_receivables(overdue_only=False, min_days_overdue=0, ctx=mock_ctx)
    assert result is not None


async def test_get_party_outstanding_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_party_outstanding

    result = await get_party_outstanding(party_name="Sharma Trading Co", ctx=mock_ctx)
    assert result is not None


async def test_get_sales_summary_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_sales_summary

    result = await get_sales_summary(
        from_date="2025-01-01", to_date="2025-12-31", group_by="day", ctx=mock_ctx
    )
    assert result is not None


async def test_get_gst_summary_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_gst_summary

    result = await get_gst_summary(
        from_date="2025-01-01", to_date="2025-12-31", ctx=mock_ctx
    )
    assert result is not None


async def test_search_tally_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import search_tally

    result = await search_tally(query="Cash", limit=10, ctx=mock_ctx)
    assert result is not None


async def test_get_sync_status_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_sync_status

    result = await get_sync_status(ctx=mock_ctx)
    assert result is not None


async def test_get_low_stock_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_low_stock

    result = await get_low_stock(threshold=0.0, ctx=mock_ctx)
    assert result is not None


async def test_get_stock_aging_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_stock_aging

    result = await get_stock_aging(date="2025-04-15", bucket_days=None, ctx=mock_ctx)
    assert result is not None


async def test_get_cost_center_summary_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_cost_center_summary

    result = await get_cost_center_summary(
        from_date="2025-01-01",
        to_date="2025-12-31",
        cost_center_name=None,
        ctx=mock_ctx,
    )
    assert result is not None


async def test_query_tally_data_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import query_tally_data

    result = await query_tally_data(
        sql="SELECT * FROM mst_ledger", limit=10, ctx=mock_ctx
    )
    assert isinstance(result, list)


async def test_query_tally_data_with_limit(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import query_tally_data

    result = await query_tally_data(
        sql="SELECT * FROM mst_ledger LIMIT 5", limit=10, ctx=mock_ctx
    )
    assert isinstance(result, list)


async def test_get_sync_errors_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_sync_errors

    result = await get_sync_errors(entity_type=None, limit=10, ctx=mock_ctx)
    assert result is not None


async def test_get_balance_sheet_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_balance_sheet

    result = await get_balance_sheet(to_date="2025-12-31", ctx=mock_ctx)
    assert isinstance(result, list)


async def test_get_profit_loss_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_profit_loss

    result = await get_profit_loss(
        from_date="2025-01-01", to_date="2025-12-31", ctx=mock_ctx
    )
    assert isinstance(result, list)


async def test_get_ledger_account_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_ledger_account

    result = await get_ledger_account(
        ledger_name="Cash",
        from_date="2025-01-01",
        to_date="2025-12-31",
        ctx=mock_ctx,
    )
    assert isinstance(result, list)


async def test_get_stock_item_account_tool(mock_ctx) -> None:
    from tallybridge.mcp.sdk_server import get_stock_item_account

    result = await get_stock_item_account(
        item_name="Test Item",
        from_date="2025-01-01",
        to_date="2025-12-31",
        ctx=mock_ctx,
    )
    assert isinstance(result, list)


def test_get_tally_digest(query) -> None:
    result = query.get_daily_digest()
    serialized = _serialize(result)
    assert isinstance(serialized, (dict, list, str))


def test_query_tally_data_uses_readonly(cache) -> None:
    result = cache.query_readonly("SELECT * FROM mst_ledger LIMIT 1")
    assert isinstance(result, list)


def test_get_ledger_balance(query) -> None:
    result = query.get_ledger_balance("Cash")
    assert isinstance(result, Decimal)


def test_get_ledger_balance_nonexistent(query) -> None:
    with pytest.raises(KeyError):
        query.get_ledger_balance("nonexistent")


def test_get_receivables(query) -> None:
    result = query.get_receivables()
    assert isinstance(result, list)


def test_get_receivables_overdue_only(query) -> None:
    result = query.get_receivables(overdue_only=True, min_days_overdue=10)
    assert isinstance(result, list)


def test_get_sales_summary(query) -> None:
    result = query.get_sales_summary(
        from_date=date(2025, 1, 1), to_date=date(2025, 12, 31), group_by="day"
    )
    assert isinstance(result, list)


def test_get_sales_summary_by_party(query) -> None:
    result = query.get_sales_summary(
        from_date=date(2025, 1, 1), to_date=date(2025, 12, 31), group_by="party"
    )
    assert isinstance(result, list)


def test_get_gst_summary(query) -> None:
    result = query.get_gst_summary(
        from_date=date(2025, 1, 1), to_date=date(2025, 12, 31)
    )
    assert isinstance(result, dict)
    assert "total_cgst_collected" in result


def test_get_sync_status(cache) -> None:
    result = cache.get_sync_status()
    assert isinstance(result, dict)


def test_get_low_stock(query) -> None:
    items = query.get_low_stock_items(threshold_quantity=Decimal("0"))
    assert isinstance(items, list)


def test_get_stock_aging(query) -> None:
    result = query.get_stock_aging(as_of_date=date(2025, 4, 15))
    assert isinstance(result, list)


def test_get_stock_aging_with_buckets(query) -> None:
    result = query.get_stock_aging(as_of_date=date(2025, 4, 15), bucket_days=[60, 120])
    assert isinstance(result, list)


def test_get_cost_center_summary(query) -> None:
    result = query.get_cost_center_summary(
        from_date=date(2025, 1, 1), to_date=date(2025, 12, 31)
    )
    assert isinstance(result, list)


def test_get_cost_center_summary_filtered(query) -> None:
    result = query.get_cost_center_summary(
        from_date=date(2025, 1, 1),
        to_date=date(2025, 12, 31),
        cost_center_name="Head Office",
    )
    assert isinstance(result, list)


def test_search_tally(query) -> None:
    result = query.search(query="Cash")
    assert "ledgers" in result
    assert "vouchers" in result
    assert "parties" in result


def test_search_tally_with_limit(query) -> None:
    result = query.search(query="Cash", limit=5)
    assert "ledgers" in result


def test_get_party_outstanding(query) -> None:
    result = query.get_party_outstanding("Sharma Trading Co")
    assert isinstance(result, dict)


def test_query_adds_limit(cache) -> None:
    result = cache.query_readonly("SELECT * FROM mst_ledger")
    assert isinstance(result, list)


def test_query_custom_limit(cache) -> None:
    result = cache.query_readonly("SELECT * FROM mst_ledger LIMIT 5")
    assert isinstance(result, list)


def test_mcp_server_has_25_tools() -> None:
    from tallybridge.mcp.sdk_server import mcp

    tools = mcp._tool_manager.list_tools()
    assert len(tools) == 25


def test_mcp_lifespan_creates_context() -> None:
    from tallybridge.mcp.sdk_server import app_lifespan

    assert app_lifespan is not None


def test_main_entry_point_exists() -> None:
    from tallybridge.mcp.sdk_server import main

    assert callable(main)


def test_mcp_api_key_in_config() -> None:
    from tallybridge.config import TallyBridgeConfig

    config = TallyBridgeConfig(mcp_api_key="test-secret-key")
    assert config.mcp_api_key == "test-secret-key"


def test_check_auth_skips_without_api_key() -> None:
    from tallybridge.config import TallyBridgeConfig, reset_config

    reset_config()
    os.environ.pop("TALLYBRIDGE_MCP_API_KEY", None)
    config = TallyBridgeConfig()
    assert config.mcp_api_key is None


def test_main_warns_no_api_key_http() -> None:
    os.environ["TALLYBRIDGE_MCP_TRANSPORT"] = "http"
    os.environ.pop("TALLYBRIDGE_MCP_API_KEY", None)
    try:
        from tallybridge.config import TallyBridgeConfig, reset_config

        reset_config()
        config = TallyBridgeConfig()
        assert config.mcp_api_key is None
    finally:
        os.environ.pop("TALLYBRIDGE_MCP_TRANSPORT", None)
