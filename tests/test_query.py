"""Tests for query — SPECS.md §8."""

from datetime import date
from decimal import Decimal

import pytest

from tallybridge.query import TallyQuery


def test_get_daily_digest(tally_query: TallyQuery) -> None:
    digest = tally_query.get_daily_digest(date(2025, 4, 15))
    assert digest.total_sales > 0
    assert digest.cash_balance > 0


def test_get_daily_digest_empty_db(tmp_db) -> None:
    q = TallyQuery(tmp_db)
    digest = q.get_daily_digest()
    assert digest.total_sales == Decimal("0")


def test_get_daily_digest_excludes_cancelled(tally_query: TallyQuery) -> None:
    digest = tally_query.get_daily_digest(date(2025, 12, 31))
    cancelled_sales = Decimal("15000")
    expected = Decimal("50000") + Decimal("35000") + Decimal("25000")
    assert digest.total_sales == expected


def test_get_ledger_balance(tally_query: TallyQuery) -> None:
    balance = tally_query.get_ledger_balance("Cash")
    assert balance == Decimal("45000")


def test_get_ledger_balance_nonexistent(tally_query: TallyQuery) -> None:
    with pytest.raises(KeyError):
        tally_query.get_ledger_balance("nonexistent")


def test_get_cash_balance(tally_query: TallyQuery) -> None:
    assert tally_query.get_cash_balance() > 0


def test_get_bank_balance(tally_query: TallyQuery) -> None:
    assert tally_query.get_bank_balance() > 0


def test_get_receivables(tally_query: TallyQuery) -> None:
    recs = tally_query.get_receivables()
    assert len(recs) > 0


def test_get_receivables_overdue_only(tally_query: TallyQuery) -> None:
    recs = tally_query.get_receivables(overdue_only=True)
    for r in recs:
        assert r.overdue_days > 0


def test_get_payables(tally_query: TallyQuery) -> None:
    pays = tally_query.get_payables()
    assert len(pays) > 0


def test_get_party_outstanding(tally_query: TallyQuery) -> None:
    result = tally_query.get_party_outstanding("Sharma Trading Co")
    assert "total_receivable" in result
    assert "total_payable" in result
    assert "net_position" in result


def test_get_sales_summary_by_party(tally_query: TallyQuery) -> None:
    summary = tally_query.get_sales_summary(date(2025, 1, 1), date(2025, 12, 31), group_by="party")
    assert len(summary) > 0
    parties = {r["party_name"] for r in summary}
    assert "Sharma Trading Co" in parties


def test_get_sales_summary_by_day(tally_query: TallyQuery) -> None:
    summary = tally_query.get_sales_summary(date(2025, 1, 1), date(2025, 12, 31), group_by="day")
    assert len(summary) > 0


def test_get_purchases_summary(tally_query: TallyQuery) -> None:
    summary = tally_query.get_purchases_summary(date(2025, 1, 1), date(2025, 12, 31))
    assert len(summary) > 0


def test_get_vouchers_excludes_cancelled(tally_query: TallyQuery) -> None:
    vouchers = tally_query.get_vouchers()
    for v in vouchers:
        assert not v.is_cancelled
        assert not v.is_void


def test_get_vouchers_by_type(tally_query: TallyQuery) -> None:
    vouchers = tally_query.get_vouchers(voucher_type="Sales")
    for v in vouchers:
        assert v.voucher_type == "Sales"


def test_get_stock_summary(tally_query: TallyQuery) -> None:
    summary = tally_query.get_stock_summary()
    assert len(summary) > 0


def test_get_low_stock_items(tally_query: TallyQuery) -> None:
    items = tally_query.get_low_stock_items()
    assert any(i.name == "Widget C" for i in items)


def test_get_stock_aging(tally_query: TallyQuery) -> None:
    aging = tally_query.get_stock_aging()
    assert len(aging) > 0
    for line in aging:
        assert line.aging_bucket != ""


def test_get_stock_aging_custom_buckets(tally_query: TallyQuery) -> None:
    aging = tally_query.get_stock_aging(bucket_days=[60, 120])
    assert len(aging) > 0


def test_get_gst_summary(tally_query: TallyQuery) -> None:
    summary = tally_query.get_gst_summary(date(2025, 1, 1), date(2025, 12, 31))
    assert "total_cgst_collected" in summary
    assert "net_liability" in summary


def test_get_cost_center_summary(tally_query: TallyQuery) -> None:
    summary = tally_query.get_cost_center_summary(date(2025, 1, 1), date(2025, 12, 31))
    assert isinstance(summary, list)
    if len(summary) > 0:
        assert "cost_center" in summary[0]
        assert "net" in summary[0]


def test_search_ledgers(tally_query: TallyQuery) -> None:
    results = tally_query.search("sharma")
    assert len(results["ledgers"]) > 0 or len(results["parties"]) > 0


def test_search_empty(tally_query: TallyQuery) -> None:
    results = tally_query.search("")
    assert results["ledgers"] == []
    assert results["vouchers"] == []


def test_search_no_match(tally_query: TallyQuery) -> None:
    results = tally_query.search("zzznonexistent")
    assert len(results["ledgers"]) == 0
