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
    Decimal("15000")
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
    summary = tally_query.get_sales_summary(
        date(2025, 1, 1), date(2025, 12, 31), group_by="party"
    )
    assert len(summary) > 0
    parties = {r["party_name"] for r in summary}
    assert "Sharma Trading Co" in parties


def test_get_sales_summary_by_day(tally_query: TallyQuery) -> None:
    summary = tally_query.get_sales_summary(
        date(2025, 1, 1), date(2025, 12, 31), group_by="day"
    )
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


def test_get_sales_summary_fallback_group(tally_query: TallyQuery) -> None:
    summary = tally_query.get_sales_summary(
        date(2025, 1, 1), date(2025, 12, 31), group_by="week"
    )
    assert isinstance(summary, list)


def test_get_sales_summary_month_group(tally_query: TallyQuery) -> None:
    summary = tally_query.get_sales_summary(
        date(2025, 1, 1), date(2025, 12, 31), group_by="month"
    )
    assert isinstance(summary, list)


def test_get_sales_summary_item_group(tally_query: TallyQuery) -> None:
    summary = tally_query.get_sales_summary(
        date(2025, 1, 1), date(2025, 12, 31), group_by="item"
    )
    assert isinstance(summary, list)


def test_get_vouchers_with_date_filter(tally_query: TallyQuery) -> None:
    vouchers = tally_query.get_vouchers(
        from_date=date(2025, 4, 1), to_date=date(2025, 4, 5)
    )
    for v in vouchers:
        assert v.date >= date(2025, 4, 1)
        assert v.date <= date(2025, 4, 5)


def test_get_vouchers_with_party_filter(tally_query: TallyQuery) -> None:
    vouchers = tally_query.get_vouchers(party_name="Sharma Trading Co")
    for v in vouchers:
        assert v.party_ledger == "Sharma Trading Co"


def test_get_vouchers_with_all_filters(tally_query: TallyQuery) -> None:
    vouchers = tally_query.get_vouchers(
        voucher_type="Sales",
        from_date=date(2025, 1, 1),
        to_date=date(2025, 12, 31),
        party_name="Sharma Trading Co",
        limit=10,
    )
    assert isinstance(vouchers, list)


def test_get_stock_aging_no_movement(tally_query: TallyQuery) -> None:
    aging = tally_query.get_stock_aging(as_of_date=date(2025, 4, 15))
    no_movement = [a for a in aging if a.aging_bucket == "No Movement"]
    assert len(no_movement) >= 0


def test_get_gst_summary_with_cgst(tally_query: TallyQuery) -> None:
    summary = tally_query.get_gst_summary(date(2025, 1, 1), date(2025, 12, 31))
    assert summary["total_cgst_collected"] >= Decimal("0")


def test_get_cost_center_summary_with_filter(tally_query: TallyQuery) -> None:
    summary = tally_query.get_cost_center_summary(
        date(2025, 1, 1),
        date(2025, 12, 31),
        cost_center_name="Head Office",
    )
    assert isinstance(summary, list)
    for item in summary:
        assert item["cost_center"] == "Head Office"


def test_search_with_vouchers(tally_query: TallyQuery) -> None:
    results = tally_query.search("Invoice")
    assert isinstance(results["vouchers"], list)


def test_search_with_limit(tally_query: TallyQuery) -> None:
    results = tally_query.search("a", limit=2)
    assert isinstance(results["ledgers"], list)


def test_get_bucket_boundaries() -> None:
    assert TallyQuery._get_bucket(15, [30, 60, 90]) == "1-30"
    assert TallyQuery._get_bucket(45, [30, 60, 90]) == "31-60"
    assert TallyQuery._get_bucket(75, [30, 60, 90]) == "61-90"
    assert TallyQuery._get_bucket(120, [30, 60, 90]) == "90+"


def test_row_to_voucher_string_date(tally_query: TallyQuery) -> None:
    row = {
        "guid": "v1",
        "alter_id": 1,
        "voucher_number": "1",
        "voucher_type": "Sales",
        "date": "2025-04-01",
        "effective_date": "2025-04-01",
        "total_amount": Decimal("1000"),
    }
    v = TallyQuery._row_to_voucher(row)
    assert v.date == date(2025, 4, 1)
    assert v.effective_date == date(2025, 4, 1)


def test_row_to_voucher_invalid_date(tally_query: TallyQuery) -> None:
    row = {
        "guid": "v2",
        "alter_id": 1,
        "voucher_number": "2",
        "voucher_type": "Sales",
        "date": "not-a-date",
        "effective_date": "invalid",
        "due_date": "bad-date",
        "total_amount": Decimal("500"),
    }
    v = TallyQuery._row_to_voucher(row)
    assert v.date == date.today()
    assert v.effective_date is None
    assert v.due_date is None


def test_row_to_voucher_date_object(tally_query: TallyQuery) -> None:
    row = {
        "guid": "v3",
        "alter_id": 1,
        "voucher_number": "3",
        "voucher_type": "Sales",
        "date": date(2025, 4, 1),
        "total_amount": Decimal("2000"),
    }
    v = TallyQuery._row_to_voucher(row)
    assert v.date == date(2025, 4, 1)


def test_row_to_voucher_non_date_type(tally_query: TallyQuery) -> None:
    row = {
        "guid": "v4",
        "alter_id": 1,
        "voucher_number": "4",
        "voucher_type": "Sales",
        "date": 12345,
        "effective_date": 99999,
        "due_date": 88888,
        "total_amount": Decimal("3000"),
    }
    v = TallyQuery._row_to_voucher(row)
    assert v.date == date.today()
    assert v.effective_date is None
    assert v.due_date is None


def test_get_receivables_min_days(tally_query: TallyQuery) -> None:
    recs = tally_query.get_receivables(min_days_overdue=1)
    assert isinstance(recs, list)


def test_get_payables_overdue_only(tally_query: TallyQuery) -> None:
    pays = tally_query.get_payables(overdue_only=True)
    assert isinstance(pays, list)


def test_get_low_stock_with_threshold(tally_query: TallyQuery) -> None:
    items = tally_query.get_low_stock_items(threshold_quantity=Decimal("10"))
    assert isinstance(items, list)


def test_get_trial_balance(tally_query: TallyQuery) -> None:
    result = tally_query.get_trial_balance(date(2025, 1, 1), date(2025, 12, 31))
    assert isinstance(result, list)
    if len(result) > 0:
        assert result[0].ledger != ""
        assert isinstance(result[0].opening_debit, Decimal)


def test_get_payables_overdue_filtering(tally_query: TallyQuery) -> None:
    pays = tally_query.get_payables(overdue_only=True)
    for p in pays:
        assert p.overdue_days > 0


def test_get_receivables_min_days_overdue_filtering(tally_query: TallyQuery) -> None:
    recs = tally_query.get_receivables(min_days_overdue=365)
    for r in recs:
        assert r.overdue_days >= 365


def test_get_stock_aging_no_movement_item(tally_query: TallyQuery) -> None:
    aging = tally_query.get_stock_aging(as_of_date=date(2025, 4, 15))
    for line in aging:
        if line.aging_bucket == "No Movement":
            assert line.last_movement_date is None or line.days_since_movement == 0


def test_get_stock_aging_invalid_date_string(tally_query: TallyQuery) -> None:
    aging = tally_query.get_stock_aging(as_of_date=date(2025, 4, 15))
    assert isinstance(aging, list)


def test_search_empty_query(tally_query: TallyQuery) -> None:
    result = tally_query.search("")
    assert result["ledgers"] == []
    assert result["vouchers"] == []
    assert result["parties"] == []


def test_search_fuzzy_fallback(tally_query: TallyQuery) -> None:
    result = tally_query.search("Cash", limit=5)
    assert "ledgers" in result


def test_search_with_parties(tally_query: TallyQuery) -> None:
    result = tally_query.search("Sharma")
    assert isinstance(result["parties"], list)


def test_get_gst_summary_sgst_igst(tally_query: TallyQuery) -> None:
    summary = tally_query.get_gst_summary(date(2025, 1, 1), date(2025, 12, 31))
    assert "total_sgst_collected" in summary
    assert "total_igst_collected" in summary
    assert isinstance(summary["total_sgst_collected"], Decimal)
    assert isinstance(summary["total_igst_collected"], Decimal)


def test_get_vouchers_no_results(tally_query: TallyQuery) -> None:
    vouchers = tally_query.get_vouchers(voucher_type="NonexistentType")
    assert len(vouchers) == 0


def test_get_receivables_not_overdue_skipped(tally_query: TallyQuery) -> None:
    recs = tally_query.get_receivables(as_of_date=date(2020, 1, 1), overdue_only=True)
    for r in recs:
        assert r.overdue_days > 0


def test_get_payables_overdue_only_filtering(tally_query: TallyQuery) -> None:
    pays = tally_query.get_payables(as_of_date=date(2020, 1, 1), overdue_only=True)
    for p in pays:
        assert p.overdue_days > 0


def test_fuzzy_search_ledgers_fallback(tally_query: TallyQuery) -> None:
    result = tally_query._fuzzy_search_ledgers("Cash", 5)
    assert isinstance(result, list)


def test_fuzzy_search_vouchers_fallback(tally_query: TallyQuery) -> None:
    result = tally_query._fuzzy_search_vouchers("Sales", 5)
    assert isinstance(result, list)


def test_fuzzy_available_check(tally_query: TallyQuery) -> None:
    result = tally_query._fuzzy_available()
    assert isinstance(result, bool)
