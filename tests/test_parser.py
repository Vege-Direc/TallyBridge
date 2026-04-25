"""Tests for parser — SPECS.md §5."""

from datetime import date
from decimal import Decimal

from tallybridge.parser import TallyXMLParser
from tests.mock_tally import (
    build_ledger_xml,
    build_group_xml,
    build_voucher_xml,
    build_stock_item_xml,
    build_unit_xml,
    build_stock_group_xml,
    build_cost_center_xml,
    SAMPLE_LEDGERS,
)


parser = TallyXMLParser()


def test_parse_amount_dr() -> None:
    assert parser.parse_amount("1234.56 Dr") == Decimal("1234.56")


def test_parse_amount_cr() -> None:
    assert parser.parse_amount("1234.56 Cr") == Decimal("-1234.56")


def test_parse_amount_negative() -> None:
    assert parser.parse_amount("-500.00") == Decimal("-500.00")


def test_parse_amount_empty() -> None:
    assert parser.parse_amount("") == Decimal("0")


def test_parse_amount_none() -> None:
    assert parser.parse_amount(None) == Decimal("0")


def test_parse_date_valid() -> None:
    assert parser.parse_date("20250415") == date(2025, 4, 15)


def test_parse_date_empty() -> None:
    assert parser.parse_date("") is None


def test_parse_date_none() -> None:
    assert parser.parse_date(None) is None


def test_parse_bool_yes() -> None:
    assert parser.parse_bool("Yes") is True


def test_parse_bool_no() -> None:
    assert parser.parse_bool("No") is False


def test_parse_bool_none() -> None:
    assert parser.parse_bool(None) is False


def test_parse_ledgers() -> None:
    xml = build_ledger_xml()
    ledgers = parser.parse_ledgers(xml)
    assert len(ledgers) >= 3
    cash = [l for l in ledgers if l.name == "Cash"][0]
    assert cash.parent_group == "Cash-in-Hand"
    assert cash.closing_balance == Decimal("45000")


def test_parse_ledgers_unicode() -> None:
    xml = build_ledger_xml()
    ledgers = parser.parse_ledgers(xml)
    hindi = [l for l in ledgers if "शर्मा" in l.name]
    assert len(hindi) >= 1


def test_parse_vouchers_with_ledger_entries() -> None:
    xml = build_voucher_xml()
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) >= 1
    v = vouchers[0]
    assert len(v.ledger_entries) >= 2


def test_parse_vouchers_cancelled() -> None:
    xml = build_voucher_xml()
    vouchers = parser.parse_vouchers(xml)
    cancelled = [v for v in vouchers if v.is_cancelled]
    assert len(cancelled) >= 1
    assert cancelled[0].is_cancelled is True


def test_parse_groups() -> None:
    xml = build_group_xml()
    groups = parser.parse_groups(xml)
    assert len(groups) >= 3


def test_parse_stock_items() -> None:
    xml = build_stock_item_xml()
    items = parser.parse_stock_items(xml)
    assert len(items) >= 3
    widget_a = [i for i in items if i.name == "Widget A"][0]
    assert widget_a.unit == "Nos"


def test_parse_units() -> None:
    xml = build_unit_xml()
    units = parser.parse_units(xml)
    assert len(units) >= 4


def test_parse_stock_groups() -> None:
    xml = build_stock_group_xml()
    groups = parser.parse_stock_groups(xml)
    assert len(groups) >= 2


def test_parse_cost_centers() -> None:
    xml = build_cost_center_xml()
    centers = parser.parse_cost_centers(xml)
    assert len(centers) >= 3


def test_parse_malformed_xml_returns_empty() -> None:
    assert parser.parse_ledgers("not xml at all") == []
    assert parser.parse_groups("not xml at all") == []
    assert parser.parse_vouchers("not xml at all") == []
    assert parser.parse_stock_items("not xml at all") == []
