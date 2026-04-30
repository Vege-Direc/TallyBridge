"""Tests for e-invoice JSON export builder — see SPECS.md §34."""

from datetime import date
from decimal import Decimal

import pytest

from tallybridge.cache import TallyCache
from tallybridge.einvoice import EInvoiceBuilder
from tallybridge.models.master import TallyLedger, TallyStockItem
from tallybridge.models.voucher import (
    TallyInventoryEntry,
    TallyVoucher,
    TallyVoucherEntry,
)


@pytest.fixture
def populated_cache(tmp_path) -> TallyCache:
    db = TallyCache(str(tmp_path / "test.duckdb"))
    db.upsert_ledgers(
        [
            TallyLedger(
                name="Cash",
                guid="g-cash",
                alter_id=1,
                parent_group="Cash-in-Hand",
            ),
            TallyLedger(
                name="Sales",
                guid="g-sales",
                alter_id=2,
                parent_group="Sales Accounts",
                gstin="27AABCS1429B1Z1",
            ),
            TallyLedger(
                name="Sharma Trading",
                guid="g-party",
                alter_id=3,
                parent_group="Sundry Debtors",
                gstin="27AAACM2850K1Z1",
            ),
            TallyLedger(
                name="CGST",
                guid="g-cgst",
                alter_id=4,
                parent_group="Duties & Taxes",
            ),
            TallyLedger(
                name="SGST",
                guid="g-sgst",
                alter_id=5,
                parent_group="Duties & Taxes",
            ),
        ]
    )
    db.upsert_stock_items(
        [
            TallyStockItem(
                name="Widget A",
                guid="g-wa",
                alter_id=10,
                parent_group="Finished Goods",
                unit="Nos",
                hsn_code="8479",
            ),
        ]
    )
    return db


@pytest.fixture
def builder(populated_cache: TallyCache) -> EInvoiceBuilder:
    return EInvoiceBuilder(populated_cache)


def _make_sales_voucher() -> TallyVoucher:
    return TallyVoucher(
        guid="v-einv-001",
        alter_id=600,
        voucher_number="SI/EINV/001",
        voucher_type="Sales",
        date=date(2026, 4, 1),
        party_ledger="Sharma Trading",
        party_gstin="27AAACM2850K1Z1",
        place_of_supply="27-Maharashtra",
        ledger_entries=[
            TallyVoucherEntry(ledger_name="Sharma Trading", amount=Decimal("59000")),
            TallyVoucherEntry(ledger_name="Sales", amount=Decimal("-50000")),
            TallyVoucherEntry(ledger_name="CGST", amount=Decimal("-4500")),
            TallyVoucherEntry(ledger_name="SGST", amount=Decimal("-4500")),
        ],
        inventory_entries=[
            TallyInventoryEntry(
                stock_item_name="Widget A",
                quantity=Decimal("10"),
                rate=Decimal("5000"),
                amount=Decimal("50000"),
            ),
        ],
        total_amount=Decimal("59000"),
        gst_amount=Decimal("9000"),
    )


def test_build_einvoice_json_basic(builder: EInvoiceBuilder) -> None:
    voucher = _make_sales_voucher()
    result = builder.build_einvoice_json(voucher)

    assert result["Version"] == "1.1"
    assert result["TranDtls"]["TaxSch"] == "GST"
    assert result["DocDtls"]["No"] == "SI/EINV/001"
    assert result["DocDtls"]["Dt"] == "01/04/2026"
    assert len(result["ItemList"]) == 1
    assert result["ItemList"][0]["HsnCd"] == "8479"
    assert result["ValDtls"]["CgstVal"] == "4500"
    assert result["ValDtls"]["SgstVal"] == "4500"


def test_build_einvoice_json_missing_gstin(builder: EInvoiceBuilder) -> None:
    voucher = TallyVoucher(
        guid="v-no-gstin",
        alter_id=601,
        voucher_number="SI/002",
        voucher_type="Sales",
        date=date(2026, 4, 5),
        party_ledger="Unknown Party",
        total_amount=Decimal("1000"),
    )
    with pytest.raises(ValueError, match="Buyer GSTIN"):
        builder.build_einvoice_json(voucher)


def test_build_einvoice_json_with_igst(builder: EInvoiceBuilder) -> None:
    voucher = TallyVoucher(
        guid="v-igst",
        alter_id=602,
        voucher_number="SI/IGST/001",
        voucher_type="Sales",
        date=date(2026, 4, 10),
        party_ledger="Sharma Trading",
        party_gstin="29AAACM2850K1Z1",
        place_of_supply="29-Karnataka",
        ledger_entries=[
            TallyVoucherEntry(
                ledger_name="Sharma Trading", amount=Decimal("59000")
            ),
            TallyVoucherEntry(ledger_name="Sales", amount=Decimal("-50000")),
            TallyVoucherEntry(ledger_name="IGST", amount=Decimal("-9000")),
        ],
        total_amount=Decimal("59000"),
        gst_amount=Decimal("9000"),
    )
    result = builder.build_einvoice_json(voucher)
    assert result["ValDtls"]["IgstVal"] == "9000"
    assert result["ValDtls"]["CgstVal"] == "0"


def test_validate_einvoice_data_valid(builder: EInvoiceBuilder) -> None:
    voucher = _make_sales_voucher()
    result = builder.validate_einvoice_data(voucher)
    assert result.valid


def test_validate_einvoice_data_missing_invoice_number(
    builder: EInvoiceBuilder,
) -> None:
    voucher = TallyVoucher(
        guid="v-no-num",
        alter_id=603,
        voucher_number="",
        voucher_type="Sales",
        date=date(2026, 4, 1),
        party_ledger="Sharma Trading",
        party_gstin="27AAACM2850K1Z1",
    )
    result = builder.validate_einvoice_data(voucher)
    assert not result.valid
    assert any("Invoice number" in e for e in result.errors)


def test_validate_einvoice_data_missing_hsn_warning(
    builder: EInvoiceBuilder,
) -> None:
    voucher = TallyVoucher(
        guid="v-no-hsn",
        alter_id=604,
        voucher_number="SI/003",
        voucher_type="Sales",
        date=date(2026, 4, 1),
        party_ledger="Sharma Trading",
        party_gstin="27AAACM2850K1Z1",
        inventory_entries=[
            TallyInventoryEntry(
                stock_item_name="Unknown Item",
                quantity=Decimal("1"),
                rate=Decimal("100"),
                amount=Decimal("100"),
            ),
        ],
    )
    result = builder.validate_einvoice_data(voucher)
    assert result.valid
    assert any("HSN code missing" in w for w in result.warnings)


def test_build_batch_json(builder: EInvoiceBuilder) -> None:
    v1 = _make_sales_voucher()
    v2 = TallyVoucher(
        guid="v-no-gstin",
        alter_id=605,
        voucher_number="",
        voucher_type="Sales",
        date=date(2026, 4, 5),
        total_amount=Decimal("100"),
    )
    results = builder.build_batch_json([v1, v2])
    assert len(results) == 1
    assert results[0]["DocDtls"]["No"] == "SI/EINV/001"


def test_build_einvoice_service_invoice(builder: EInvoiceBuilder) -> None:
    voucher = TallyVoucher(
        guid="v-service",
        alter_id=606,
        voucher_number="SI/SVC/001",
        voucher_type="Sales",
        date=date(2026, 4, 15),
        party_ledger="Sharma Trading",
        party_gstin="27AAACM2850K1Z1",
        place_of_supply="27-Maharashtra",
        narration="Consulting services",
        ledger_entries=[
            TallyVoucherEntry(
                ledger_name="Sharma Trading", amount=Decimal("11800")
            ),
            TallyVoucherEntry(ledger_name="Sales", amount=Decimal("-10000")),
            TallyVoucherEntry(ledger_name="CGST", amount=Decimal("-900")),
            TallyVoucherEntry(ledger_name="SGST", amount=Decimal("-900")),
        ],
        total_amount=Decimal("11800"),
        gst_amount=Decimal("1800"),
    )
    result = builder.build_einvoice_json(voucher)
    assert result["ItemList"][0]["PrdDesc"] == "Consulting services"
