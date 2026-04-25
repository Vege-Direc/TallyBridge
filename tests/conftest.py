"""Shared test fixtures — see SPECS.md §11b."""

from datetime import date
from decimal import Decimal

import pytest
from pytest_httpserver import HTTPServer

from tallybridge.cache import TallyCache
from tallybridge.config import TallyBridgeConfig
from tallybridge.connection import TallyConnection
from tallybridge.models.master import (
    TallyCostCenter,
    TallyGroup,
    TallyLedger,
    TallyStockGroup,
    TallyStockItem,
    TallyUnit,
    TallyVoucherType,
)
from tallybridge.models.voucher import TallyInventoryEntry, TallyVoucher, TallyVoucherEntry
from tallybridge.query import TallyQuery
from tests.mock_tally import (
    SAMPLE_COST_CENTERS,
    SAMPLE_GROUPS,
    SAMPLE_LEDGERS,
    SAMPLE_STOCK_GROUPS,
    SAMPLE_STOCK_ITEMS,
    SAMPLE_UNITS,
    SAMPLE_VOUCHERS,
    setup_mock_routes,
)


@pytest.fixture(scope="session")
def mock_tally_server(httpserver: HTTPServer):
    """Running mock Tally HTTP server with all sample data routes."""
    setup_mock_routes(httpserver)
    return httpserver


@pytest.fixture
def tmp_db(tmp_path):
    """Fresh TallyCache with schema initialised, empty data."""
    cache = TallyCache(str(tmp_path / "test.duckdb"))
    yield cache
    cache.close()


@pytest.fixture
def populated_db(tmp_db):
    """TallyCache pre-loaded with all SAMPLE_* data via upsert methods."""
    for guid, alter_id, name, parent, primary, is_revenue, net_dc in SAMPLE_GROUPS:
        tmp_db.upsert_groups([
            TallyGroup(
                guid=guid, alter_id=alter_id, name=name,
                parent=parent, primary_group=primary,
                is_revenue=is_revenue, net_debit_credit=net_dc,
            )
        ])

    for guid, alter_id, name, parent, closing, is_revenue, gstin in SAMPLE_LEDGERS:
        from tallybridge.parser import TallyXMLParser
        closing_bal = TallyXMLParser.parse_amount(closing)
        tmp_db.upsert_ledgers([
            TallyLedger(
                guid=guid, alter_id=alter_id, name=name,
                parent_group=parent, closing_balance=closing_bal,
                is_revenue=is_revenue, gstin=gstin, party_name=name,
            )
        ])

    for guid, alter_id, name, unit_type, symbol, decimal_places in SAMPLE_UNITS:
        tmp_db.upsert_units([
            TallyUnit(
                guid=guid, alter_id=alter_id, name=name,
                unit_type=unit_type, symbol=symbol,
                decimal_places=decimal_places,
            )
        ])

    for guid, alter_id, name, parent, should_add in SAMPLE_STOCK_GROUPS:
        tmp_db.upsert_stock_groups([
            TallyStockGroup(
                guid=guid, alter_id=alter_id, name=name,
                parent=parent, should_quantities_add=should_add,
            )
        ])

    for guid, alter_id, name, parent, unit, gst_rate, hsn, closing_qty, closing_val in SAMPLE_STOCK_ITEMS:
        tmp_db.upsert_stock_items([
            TallyStockItem(
                guid=guid, alter_id=alter_id, name=name,
                parent_group=parent, unit=unit,
                gst_rate=Decimal(str(gst_rate)),
                hsn_code=hsn,
                closing_quantity=Decimal(str(closing_qty)),
                closing_value=Decimal(closing_val),
            )
        ])

    for guid, alter_id, name, parent, cc_type in SAMPLE_COST_CENTERS:
        tmp_db.upsert_cost_centers([
            TallyCostCenter(
                guid=guid, alter_id=alter_id, name=name,
                parent=parent, cost_centre_type=cc_type,
            )
        ])

    for (
        guid, alter_id, vtype, vdate, eff_date, party, vnum,
        amount, is_cancelled, is_void, is_postdated, entered_by,
    ) in SAMPLE_VOUCHERS:
        v = TallyVoucher(
            guid=guid,
            alter_id=alter_id,
            voucher_number=vnum,
            voucher_type=vtype,
            date=date(int(vdate[:4]), int(vdate[4:6]), int(vdate[6:8])),
            effective_date=date(int(eff_date[:4]), int(eff_date[4:6]), int(eff_date[6:8])),
            party_ledger=party,
            entered_by=entered_by,
            is_cancelled=is_cancelled,
            is_void=is_void,
            is_postdated=is_postdated,
            total_amount=Decimal(amount),
            ledger_entries=[
                TallyVoucherEntry(ledger_name=party, amount=Decimal(amount)),
                TallyVoucherEntry(
                    ledger_name="Sales" if vtype == "Sales" else "Purchase",
                    amount=Decimal("-" + amount) if vtype == "Sales" else Decimal(amount),
                ),
            ],
        )
        tmp_db.upsert_vouchers([v])

    return tmp_db


@pytest.fixture
def tally_query(populated_db):
    """TallyQuery ready to use over populated test database."""
    return TallyQuery(populated_db)


@pytest.fixture
def tally_connection(mock_tally_server):
    """TallyConnection pointing at the mock server."""
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_tally_server.port,
    )
    return TallyConnection(config)
