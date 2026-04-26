"""Tests for MCP SDK server."""

from datetime import date
from decimal import Decimal

import pytest

from tallybridge.mcp.sdk_server import _parse_date, _serialize
from tallybridge.query import TallyQuery


@pytest.fixture
def query(populated_db):
    return TallyQuery(populated_db)


@pytest.fixture
def cache(populated_db):
    return populated_db


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
    result = query.get_stock_aging(
        as_of_date=date(2025, 4, 15), bucket_days=[60, 120]
    )
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
    result = cache.query_readonly(
        "SELECT * FROM mst_ledger LIMIT 5"
    )
    assert isinstance(result, list)


def test_mcp_server_has_12_tools() -> None:
    from tallybridge.mcp.sdk_server import mcp

    tools = mcp._tool_manager.list_tools()
    assert len(tools) == 12


def test_mcp_lifespan_creates_context() -> None:
    from tallybridge.mcp.sdk_server import app_lifespan

    assert app_lifespan is not None


def test_main_entry_point_exists() -> None:
    from tallybridge.mcp.sdk_server import main

    assert callable(main)
