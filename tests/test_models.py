"""Tests for models — SPECS.md §3."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tallybridge.models.master import (
    TallyCostCenter,
    TallyGroup,
    TallyLedger,
    TallyStockGroup,
    TallyStockItem,
    TallyUnit,
    TallyVoucherType,
)
from tallybridge.models.report import (
    DailyDigest,
    OutstandingBill,
    StockAgingLine,
    SyncResult,
    TrialBalanceLine,
)
from tallybridge.models.voucher import (
    TallyInventoryEntry,
    TallyVoucher,
    TallyVoucherEntry,
)

# ── Master models ─────────────────────────────────────────────────────────


class TestMaster:
    def test_tally_ledger_instantiates(self) -> None:
        ledger = TallyLedger(
            name="Cash", guid="g1", alter_id=1, parent_group="Cash-in-Hand"
        )
        assert ledger.name == "Cash"
        assert ledger.closing_balance == Decimal("0")

    def test_tally_ledger_rejects_wrong_type(self) -> None:
        with pytest.raises(ValidationError):
            TallyLedger(name="X", guid="g", alter_id="bad", parent_group="Y")  # type: ignore[arg-type]

    def test_tally_ledger_optional_fields_default_none(self) -> None:
        ledger = TallyLedger(name="X", guid="g", alter_id=1, parent_group="Y")
        assert ledger.gstin is None
        assert ledger.party_name is None
        assert ledger.bill_credit_period is None

    def test_tally_ledger_decimal_from_string(self) -> None:
        ledger = TallyLedger(
            name="X",
            guid="g",
            alter_id=1,
            parent_group="Y",
            opening_balance="1234.56",
        )
        assert ledger.opening_balance == Decimal("1234.56")

    def test_tally_ledger_decimal_from_int(self) -> None:
        ledger = TallyLedger(
            name="X", guid="g", alter_id=1, parent_group="Y", opening_balance=100
        )
        assert ledger.opening_balance == Decimal("100")

    def test_tally_group_instantiates(self) -> None:
        group = TallyGroup(
            name="Sundry Debtors",
            guid="g2",
            alter_id=2,
            parent="Current Assets",
            primary_group="Assets",
        )
        assert group.net_debit_credit == "Dr"

    def test_tally_stock_item_instantiates(self) -> None:
        item = TallyStockItem(
            name="Widget A",
            guid="g3",
            alter_id=3,
            parent_group="Stock-in-Trade",
            unit="Nos",
        )
        assert item.closing_quantity == Decimal("0")

    def test_tally_stock_item_optional_gst_rate(self) -> None:
        item = TallyStockItem(
            name="W",
            guid="g",
            alter_id=1,
            parent_group="SG",
            unit="Nos",
            gst_rate="18.00",
        )
        assert item.gst_rate == Decimal("18.00")

    def test_tally_voucher_type_instantiates(self) -> None:
        vt = TallyVoucherType(name="Sales", guid="g4", alter_id=4, parent="Accounting")
        assert vt.number_series is None

    def test_tally_unit_compound(self) -> None:
        unit = TallyUnit(
            name="Dozen",
            guid="g5",
            alter_id=5,
            unit_type="Compound",
            base_units="Dozen of Nos",
        )
        assert unit.unit_type == "Compound"
        assert unit.base_units == "Dozen of Nos"

    def test_tally_unit_simple_defaults(self) -> None:
        unit = TallyUnit(name="Nos", guid="g", alter_id=1)
        assert unit.unit_type == "Simple"
        assert unit.decimal_places == 0
        assert unit.symbol is None

    def test_tally_stock_group_instantiates(self) -> None:
        sg = TallyStockGroup(
            name="Stock-in-Trade", guid="g6", alter_id=6, parent="Primary"
        )
        assert sg.should_quantities_add is True

    def test_tally_cost_center_all_none(self) -> None:
        cc = TallyCostCenter(name="Branch", guid="g7", alter_id=7, parent="Primary")
        assert cc.email is None
        assert cc.cost_centre_type == "Primary"


# ── Voucher models ────────────────────────────────────────────────────────


class TestVoucher:
    def test_tally_voucher_instantiates(self) -> None:
        v = TallyVoucher(
            guid="v1",
            alter_id=10,
            voucher_number="SI/001",
            voucher_type="Sales",
            date=date(2025, 4, 1),
        )
        assert v.ledger_entries == []
        assert v.inventory_entries == []

    def test_voucher_entries_not_shared_mutable_default(self) -> None:
        v1 = TallyVoucher(
            guid="v1",
            alter_id=1,
            voucher_number="1",
            voucher_type="S",
            date=date(2025, 1, 1),
        )
        v2 = TallyVoucher(
            guid="v2",
            alter_id=2,
            voucher_number="2",
            voucher_type="S",
            date=date(2025, 1, 1),
        )
        v1.ledger_entries.append(
            TallyVoucherEntry(ledger_name="Cash", amount=Decimal("100"))
        )
        assert len(v2.ledger_entries) == 0

    def test_is_cancelled_roundtrip(self) -> None:
        v = TallyVoucher(
            guid="v1",
            alter_id=1,
            voucher_number="1",
            voucher_type="Sales",
            date=date(2025, 1, 1),
            is_cancelled=True,
        )
        data = v.model_dump()
        v2 = TallyVoucher.model_validate(data)
        assert v2.is_cancelled is True

    def test_effective_date_differs_from_date(self) -> None:
        v = TallyVoucher(
            guid="v1",
            alter_id=1,
            voucher_number="1",
            voucher_type="Purchase",
            date=date(2025, 4, 3),
            effective_date=date(2025, 4, 1),
        )
        assert v.effective_date != v.date

    def test_is_postdated_and_is_void_independent(self) -> None:
        v = TallyVoucher(
            guid="v1",
            alter_id=1,
            voucher_number="1",
            voucher_type="Payment",
            date=date(2025, 5, 1),
            is_postdated=True,
            is_void=True,
        )
        assert v.is_postdated is True
        assert v.is_void is True

    def test_voucher_with_ledger_entries(self) -> None:
        v = TallyVoucher(
            guid="v1",
            alter_id=1,
            voucher_number="1",
            voucher_type="Sales",
            date=date(2025, 4, 1),
            ledger_entries=[
                TallyVoucherEntry(ledger_name="Cash", amount=Decimal("50000")),
                TallyVoucherEntry(ledger_name="Sales", amount=Decimal("-50000")),
            ],
        )
        assert len(v.ledger_entries) == 2

    def test_voucher_with_inventory_entries(self) -> None:
        v = TallyVoucher(
            guid="v1",
            alter_id=1,
            voucher_number="1",
            voucher_type="Sales",
            date=date(2025, 4, 1),
            inventory_entries=[
                TallyInventoryEntry(
                    stock_item_name="Widget A",
                    quantity=Decimal("10"),
                    rate=Decimal("500"),
                    amount=Decimal("5000"),
                ),
            ],
        )
        assert v.inventory_entries[0].stock_item_name == "Widget A"


# ── Report models ─────────────────────────────────────────────────────────


class TestReport:
    def test_trial_balance_line_instantiates(self) -> None:
        line = TrialBalanceLine(ledger="Cash", group="Cash-in-Hand")
        assert line.closing_debit == Decimal("0")

    def test_outstanding_bill_instantiates(self) -> None:
        bill = OutstandingBill(
            party_name="Sharma Trading",
            bill_date=date(2025, 4, 1),
            bill_number="SI/001",
            bill_amount=Decimal("50000"),
            outstanding_amount=Decimal("50000"),
            voucher_type="Sales",
        )
        assert bill.overdue_days == 0

    def test_daily_digest_instantiates(self) -> None:
        digest = DailyDigest(company="TestCo", digest_date=date(2025, 4, 15))
        assert digest.total_sales == Decimal("0")
        assert digest.top_overdue_receivables == []

    def test_stock_aging_line_aging_bucket(self) -> None:
        line = StockAgingLine(
            item_name="Widget A",
            unit="Nos",
            closing_quantity=Decimal("10"),
            closing_value=Decimal("5000"),
            aging_bucket="31-60",
        )
        assert line.aging_bucket == "31-60"

    def test_stock_aging_line_arbitrary_bucket(self) -> None:
        line = StockAgingLine(
            item_name="X",
            unit="Nos",
            closing_quantity=Decimal("1"),
            closing_value=Decimal("1"),
            aging_bucket="No Movement",
        )
        assert line.aging_bucket == "No Movement"

    def test_sync_result_defaults(self) -> None:
        result = SyncResult(entity_type="ledger")
        assert result.success is True
        assert result.records_synced == 0
        assert result.error_message is None

    def test_sync_result_failure(self) -> None:
        result = SyncResult(
            entity_type="voucher", success=False, error_message="connection lost"
        )
        assert result.success is False
        assert result.error_message == "connection lost"


pytestmark = []


def test_master() -> None:
    TestMaster().test_tally_ledger_instantiates()
    TestMaster().test_tally_ledger_rejects_wrong_type()
    TestMaster().test_tally_ledger_optional_fields_default_none()
    TestMaster().test_tally_ledger_decimal_from_string()
    TestMaster().test_tally_ledger_decimal_from_int()
    TestMaster().test_tally_group_instantiates()
    TestMaster().test_tally_stock_item_instantiates()
    TestMaster().test_tally_stock_item_optional_gst_rate()
    TestMaster().test_tally_voucher_type_instantiates()
    TestMaster().test_tally_unit_compound()
    TestMaster().test_tally_unit_simple_defaults()
    TestMaster().test_tally_stock_group_instantiates()
    TestMaster().test_tally_cost_center_all_none()


def test_voucher() -> None:
    TestVoucher().test_tally_voucher_instantiates()
    TestVoucher().test_voucher_entries_not_shared_mutable_default()
    TestVoucher().test_is_cancelled_roundtrip()
    TestVoucher().test_effective_date_differs_from_date()
    TestVoucher().test_is_postdated_and_is_void_independent()
    TestVoucher().test_voucher_with_ledger_entries()
    TestVoucher().test_voucher_with_inventory_entries()
