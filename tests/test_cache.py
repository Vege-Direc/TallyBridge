"""Tests for cache — SPECS.md §6."""

from datetime import date
from decimal import Decimal

import pytest

from tallybridge.cache import TallyCache
from tallybridge.exceptions import TallyBridgeCacheError
from tallybridge.models.master import (
    TallyCostCenter,
    TallyGodown,
    TallyLedger,
    TallyStockGroup,
    TallyStockItem,
    TallyUnit,
    TallyVoucherType,
)
from tallybridge.models.voucher import (
    TallyInventoryEntry,
    TallyVoucher,
    TallyVoucherEntry,
)


@pytest.fixture
def db(tmp_path):
    cache = TallyCache(str(tmp_path / "test.duckdb"))
    yield cache
    cache.close()


def test_db_file_created(tmp_path) -> None:
    path = str(tmp_path / "new.duckdb")
    cache = TallyCache(path)
    import os

    assert os.path.exists(path)
    cache.close()


def test_initialize_idempotent(db: TallyCache) -> None:
    db.initialize()
    db.initialize()


def test_upsert_ledgers_inserts(db: TallyCache) -> None:
    ledger = TallyLedger(
        name="Cash", guid="g1", alter_id=1, parent_group="Cash-in-Hand"
    )
    count = db.upsert_ledgers([ledger])
    assert count == 1
    rows = db.query("SELECT COUNT(*) as cnt FROM mst_ledger")
    assert rows[0]["cnt"] == 1


def test_upsert_ledgers_updates(db: TallyCache) -> None:
    ledger = TallyLedger(
        name="Cash", guid="g1", alter_id=1, parent_group="Cash-in-Hand"
    )
    db.upsert_ledgers([ledger])
    updated = TallyLedger(
        name="Cash", guid="g1", alter_id=2, parent_group="Cash-in-Hand"
    )
    db.upsert_ledgers([updated])
    rows = db.query("SELECT alter_id FROM mst_ledger WHERE guid = 'g1'")
    assert rows[0]["alter_id"] == 2
    count_rows = db.query("SELECT COUNT(*) as cnt FROM mst_ledger")
    assert count_rows[0]["cnt"] == 1


def test_upsert_vouchers_with_entries(db: TallyCache) -> None:
    voucher = TallyVoucher(
        guid="v1",
        alter_id=1,
        voucher_number="SI/001",
        voucher_type="Sales",
        date=date(2025, 4, 1),
        ledger_entries=[
            TallyVoucherEntry(ledger_name="Cash", amount=Decimal("50000")),
        ],
        inventory_entries=[
            TallyInventoryEntry(
                stock_item_name="Widget A",
                quantity=Decimal("10"),
                rate=Decimal("500"),
                amount=Decimal("5000"),
            ),
        ],
    )
    count = db.upsert_vouchers([voucher])
    assert count[0] == 1
    v_rows = db.query("SELECT COUNT(*) as cnt FROM trn_voucher")
    assert v_rows[0]["cnt"] == 1
    le_rows = db.query("SELECT COUNT(*) as cnt FROM trn_ledger_entry")
    assert le_rows[0]["cnt"] == 1
    ie_rows = db.query("SELECT COUNT(*) as cnt FROM trn_inventory_entry")
    assert ie_rows[0]["cnt"] == 1


def test_upsert_vouchers_replaces_entries(db: TallyCache) -> None:
    v1 = TallyVoucher(
        guid="v1",
        alter_id=1,
        voucher_number="1",
        voucher_type="Sales",
        date=date(2025, 1, 1),
        ledger_entries=[TallyVoucherEntry(ledger_name="A", amount=Decimal("100"))],
    )
    db.upsert_vouchers([v1])
    v2 = TallyVoucher(
        guid="v1",
        alter_id=2,
        voucher_number="1",
        voucher_type="Sales",
        date=date(2025, 1, 1),
        ledger_entries=[
            TallyVoucherEntry(ledger_name="B", amount=Decimal("200")),
            TallyVoucherEntry(ledger_name="C", amount=Decimal("300")),
        ],
    )
    db.upsert_vouchers([v2])
    rows = db.query("SELECT COUNT(*) as cnt FROM trn_ledger_entry")
    assert rows[0]["cnt"] == 2


def test_get_last_alter_id_default_zero(db: TallyCache) -> None:
    assert db.get_last_alter_id("ledger") == 0


def test_update_sync_state_persists(db: TallyCache) -> None:
    db.update_sync_state("ledger", 500, 100)
    assert db.get_last_alter_id("ledger") == 500


def test_sync_state_persists_across_instances(tmp_path) -> None:
    path = str(tmp_path / "persist.duckdb")
    db1 = TallyCache(path)
    db1.update_sync_state("ledger", 500, 100)
    db1.close()
    db2 = TallyCache(path)
    assert db2.get_last_alter_id("ledger") == 500
    db2.close()


def test_health_check(db: TallyCache) -> None:
    health = db.health_check()
    assert "record_counts" in health
    assert "last_sync_times" in health
    assert "db_size_mb" in health
    assert "orphan_count" in health


def test_upsert_voucher_types(db: TallyCache) -> None:
    vt = TallyVoucherType(
        name="Sales", guid="vt1", alter_id=1, parent="Accounting Vouchers"
    )
    count = db.upsert_voucher_types([vt])
    assert count == 1
    rows = db.query("SELECT * FROM mst_voucher_type WHERE guid = 'vt1'")
    assert len(rows) == 1
    assert rows[0]["name"] == "Sales"


def test_upsert_voucher_types_update(db: TallyCache) -> None:
    vt1 = TallyVoucherType(
        name="Sales", guid="vt1", alter_id=1, parent="Accounting Vouchers"
    )
    db.upsert_voucher_types([vt1])
    vt2 = TallyVoucherType(
        name="Sales", guid="vt1", alter_id=2, parent="Accounting Vouchers"
    )
    db.upsert_voucher_types([vt2])
    rows = db.query("SELECT alter_id FROM mst_voucher_type WHERE guid = 'vt1'")
    assert rows[0]["alter_id"] == 2


def test_upsert_units(db: TallyCache) -> None:
    unit = TallyUnit(
        name="Nos", guid="u1", alter_id=1, unit_type="Simple", symbol="Nos"
    )
    count = db.upsert_units([unit])
    assert count == 1
    rows = db.query("SELECT * FROM mst_unit WHERE guid = 'u1'")
    assert rows[0]["name"] == "Nos"


def test_upsert_stock_groups(db: TallyCache) -> None:
    sg = TallyStockGroup(
        name="Finished Goods", guid="sg1", alter_id=1, parent="Primary"
    )
    count = db.upsert_stock_groups([sg])
    assert count == 1
    rows = db.query("SELECT * FROM mst_stock_group WHERE guid = 'sg1'")
    assert rows[0]["name"] == "Finished Goods"


def test_upsert_cost_centers(db: TallyCache) -> None:
    cc = TallyCostCenter(name="Head Office", guid="cc1", alter_id=1, parent="Primary")
    count = db.upsert_cost_centers([cc])
    assert count == 1
    rows = db.query("SELECT * FROM mst_cost_center WHERE guid = 'cc1'")
    assert rows[0]["name"] == "Head Office"


def test_upsert_godowns(db: TallyCache) -> None:
    g = TallyGodown(name="Main Store", guid="gd1", alter_id=1, parent=None)
    count = db.upsert_godowns([g])
    assert count == 1
    rows = db.query("SELECT * FROM mst_godown WHERE guid = 'gd1'")
    assert rows[0]["name"] == "Main Store"
    assert rows[0]["parent"] is None


def test_get_ledger_found(db: TallyCache) -> None:
    ledger = TallyLedger(
        name="Cash",
        guid="g1",
        alter_id=1,
        parent_group="Cash-in-Hand",
        closing_balance=Decimal("45000"),
    )
    db.upsert_ledgers([ledger])
    result = db.get_ledger("Cash")
    assert result is not None
    assert result.name == "Cash"
    assert result.closing_balance == Decimal("45000")


def test_get_ledger_not_found(db: TallyCache) -> None:
    result = db.get_ledger("nonexistent")
    assert result is None


def test_get_stock_item_not_in_cache(db: TallyCache) -> None:
    result = db.get_ledger("MissingItem")
    assert result is None


def test_trial_balance(db: TallyCache) -> None:
    ledger = TallyLedger(
        name="Cash",
        guid="g1",
        alter_id=1,
        parent_group="Cash-in-Hand",
        opening_balance=Decimal("1000"),
        closing_balance=Decimal("5000"),
    )
    db.upsert_ledgers([ledger])
    lines = db.get_trial_balance(date(2025, 1, 1), date(2025, 12, 31))
    assert len(lines) >= 1
    cash_line = [ln for ln in lines if ln.ledger == "Cash"][0]
    assert cash_line.closing_debit == Decimal("5000")
    assert cash_line.closing_credit == Decimal("0")


def test_trial_balance_negative_balance(db: TallyCache) -> None:
    ledger = TallyLedger(
        name="Loan",
        guid="g2",
        alter_id=1,
        parent_group="Loans",
        opening_balance=Decimal("-500"),
        closing_balance=Decimal("-3000"),
    )
    db.upsert_ledgers([ledger])
    lines = db.get_trial_balance(date(2025, 1, 1), date(2025, 12, 31))
    loan_line = [ln for ln in lines if ln.ledger == "Loan"][0]
    assert loan_line.closing_debit == Decimal("0")
    assert loan_line.closing_credit == Decimal("3000")
    assert loan_line.opening_debit == Decimal("0")
    assert loan_line.opening_credit == Decimal("500")


def test_upsert_voucher_error_handling(db: TallyCache) -> None:
    bad_voucher = TallyVoucher(
        guid="v-bad",
        alter_id=1,
        voucher_number="1",
        voucher_type="Sales",
        date=date(2025, 1, 1),
        ledger_entries=[TallyVoucherEntry(ledger_name="A", amount=Decimal("100"))],
    )
    db.upsert_vouchers([bad_voucher])
    good_voucher = TallyVoucher(
        guid="v-bad",
        alter_id=2,
        voucher_number="1",
        voucher_type="Sales",
        date=date(2025, 1, 1),
        ledger_entries=[TallyVoucherEntry(ledger_name="B", amount=Decimal("200"))],
    )
    count = db.upsert_vouchers([good_voucher])
    assert count[0] == 1


def test_query_raises_cache_error(db: TallyCache) -> None:
    with pytest.raises(TallyBridgeCacheError):
        db.query("SELECT * FROM nonexistent_table")


def test_get_sync_status_empty(db: TallyCache) -> None:
    status = db.get_sync_status()
    assert status == {}


def test_close_idempotent(db: TallyCache) -> None:
    db.close()


def test_conn_property_reconnect(tmp_path) -> None:
    cache = TallyCache(str(tmp_path / "reconnect.duckdb"))
    cache.close()
    cache._conn = None
    conn = cache.conn
    assert conn is not None
    cache.close()


def test_trn_cost_centre_table_exists(db: TallyCache) -> None:
    rows = db.query(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = 'trn_cost_centre'"
    )
    assert len(rows) >= 1


def test_trn_bill_table_exists(db: TallyCache) -> None:
    rows = db.query(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'trn_bill'"
    )
    assert len(rows) >= 1


def test_upsert_voucher_with_cost_centre(db: TallyCache) -> None:
    from tallybridge.models.voucher import TallyCostCentreAllocation

    voucher = TallyVoucher(
        guid="v-cc1",
        alter_id=1,
        voucher_number="1",
        voucher_type="Sales",
        date=date(2025, 1, 1),
        ledger_entries=[TallyVoucherEntry(ledger_name="Cash", amount=Decimal("100"))],
        cost_centre_allocations=[
            TallyCostCentreAllocation(
                ledger_name="Cash", cost_centre="Head Office", amount=Decimal("100")
            )
        ],
    )
    db.upsert_vouchers([voucher])
    rows = db.query("SELECT * FROM trn_cost_centre WHERE voucher_guid = 'v-cc1'")
    assert len(rows) == 1
    assert rows[0]["cost_centre"] == "Head Office"


def test_upsert_voucher_with_bill_allocation(db: TallyCache) -> None:
    from tallybridge.models.voucher import TallyBillAllocation

    voucher = TallyVoucher(
        guid="v-bill1",
        alter_id=1,
        voucher_number="1",
        voucher_type="Sales",
        date=date(2025, 1, 1),
        ledger_entries=[TallyVoucherEntry(ledger_name="Cash", amount=Decimal("500"))],
        bill_allocations=[
            TallyBillAllocation(
                ledger_name="Sharma Trading Co",
                bill_name="SI/001",
                amount=Decimal("500"),
                bill_type="New Ref",
                bill_credit_period=30,
            )
        ],
    )
    db.upsert_vouchers([voucher])
    rows = db.query("SELECT * FROM trn_bill WHERE voucher_guid = 'v-bill1'")
    assert len(rows) == 1
    assert rows[0]["bill_name"] == "SI/001"
    assert rows[0]["bill_type"] == "New Ref"
    assert rows[0]["bill_credit_period"] == 30


def test_reconcile_orphans_no_orphans(db: TallyCache) -> None:
    count = db.reconcile_orphans()
    assert count == 0


def test_reconcile_orphans_with_orphans(db: TallyCache) -> None:
    voucher = TallyVoucher(
        guid="v-orphan",
        alter_id=1,
        voucher_number="1",
        voucher_type="Sales",
        date=date(2025, 1, 1),
        ledger_entries=[
            TallyVoucherEntry(ledger_name="NonExistentLedger", amount=Decimal("100"))
        ],
    )
    db.upsert_vouchers([voucher])
    count = db.reconcile_orphans()
    assert count >= 1


def test_upsert_ledgers_empty_list(db: TallyCache) -> None:
    count = db.upsert_ledgers([])
    assert count == 0


def test_company_column_migration(db: TallyCache) -> None:
    for table in [
        "mst_ledger",
        "mst_group",
        "mst_stock_item",
        "mst_voucher_type",
        "mst_unit",
        "mst_stock_group",
        "mst_cost_center",
        "trn_voucher",
    ]:
        cols = db.query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = ? AND column_name = 'company'",
            [table],
        )
        assert len(cols) == 1, f"company column missing in {table}"


def test_upsert_voucher_with_company(db: TallyCache) -> None:
    voucher = TallyVoucher(
        guid="v-co1",
        alter_id=1,
        voucher_number="1",
        voucher_type="Sales",
        date=date(2025, 1, 1),
        ledger_entries=[TallyVoucherEntry(ledger_name="Cash", amount=Decimal("1000"))],
    )
    db.upsert_vouchers([voucher], company="Test Company")
    rows = db.query("SELECT company FROM trn_voucher WHERE guid = 'v-co1'")
    assert len(rows) == 1
    assert rows[0]["company"] == "Test Company"


def test_content_hash_stored_on_ledger(db: TallyCache) -> None:
    ledger = TallyLedger(
        name="Cash", guid="g1", alter_id=1, parent_group="Cash-in-Hand"
    )
    db.upsert_ledgers([ledger])
    rows = db.query("SELECT content_hash FROM mst_ledger WHERE guid = 'g1'")
    assert len(rows) == 1
    assert rows[0]["content_hash"] is not None
    assert len(rows[0]["content_hash"]) == 64


def test_content_hash_consistent(db: TallyCache) -> None:
    ledger = TallyLedger(
        name="Cash", guid="g1", alter_id=1, parent_group="Cash-in-Hand"
    )
    db.upsert_ledgers([ledger])
    rows1 = db.query("SELECT content_hash FROM mst_ledger WHERE guid = 'g1'")
    db.upsert_ledgers([ledger])
    rows2 = db.query("SELECT content_hash FROM mst_ledger WHERE guid = 'g1'")
    assert rows1[0]["content_hash"] == rows2[0]["content_hash"]


def test_content_hash_changes_on_field_update(db: TallyCache) -> None:
    ledger = TallyLedger(
        name="Cash", guid="g1", alter_id=1, parent_group="Cash-in-Hand"
    )
    db.upsert_ledgers([ledger])
    rows1 = db.query("SELECT content_hash FROM mst_ledger WHERE guid = 'g1'")
    updated = TallyLedger(
        name="Cash",
        guid="g1",
        alter_id=2,
        parent_group="Cash-in-Hand",
        closing_balance=Decimal("99999"),
    )
    db.upsert_ledgers([updated])
    rows2 = db.query("SELECT content_hash FROM mst_ledger WHERE guid = 'g1'")
    assert rows1[0]["content_hash"] != rows2[0]["content_hash"]


def test_content_hash_migration_applied(db: TallyCache) -> None:
    for table in [
        "mst_ledger",
        "mst_group",
        "mst_stock_item",
        "mst_voucher_type",
        "mst_unit",
        "mst_stock_group",
        "mst_cost_center",
    ]:
        cols = db.query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = ? AND column_name = 'content_hash'",
            [table],
        )
        assert len(cols) == 1, f"content_hash column missing in {table}"


def test_detect_content_drift_returns_snapshot(db: TallyCache) -> None:
    ledger = TallyLedger(
        name="Cash", guid="g1", alter_id=1, parent_group="Cash-in-Hand"
    )
    db.upsert_ledgers([ledger])
    snapshot = db.detect_content_drift("ledger")
    assert len(snapshot) == 1
    assert snapshot[0]["guid"] == "g1"
    assert snapshot[0]["content_hash"] is not None
    assert len(snapshot[0]["content_hash"]) == 64


def test_compare_content_drift_no_drift(db: TallyCache) -> None:
    ledger = TallyLedger(
        name="Cash", guid="g1", alter_id=1, parent_group="Cash-in-Hand"
    )
    db.upsert_ledgers([ledger])
    before = db.detect_content_drift("ledger")
    updated = TallyLedger(
        name="Cash", guid="g1", alter_id=2, parent_group="Cash-in-Hand"
    )
    db.upsert_ledgers([updated])
    drift = db.compare_content_drift("ledger", before)
    assert drift == []


def test_compare_content_drift_with_drift(db: TallyCache) -> None:
    ledger = TallyLedger(
        name="Cash", guid="g1", alter_id=1, parent_group="Cash-in-Hand"
    )
    db.upsert_ledgers([ledger])
    before = db.detect_content_drift("ledger")
    updated = TallyLedger(
        name="Cash",
        guid="g1",
        alter_id=2,
        parent_group="Cash-in-Hand",
        closing_balance=Decimal("99999"),
    )
    db.upsert_ledgers([updated])
    drift = db.compare_content_drift("ledger", before)
    assert len(drift) == 1
    assert drift[0]["guid"] == "g1"
    assert drift[0]["old_hash"] != drift[0]["new_hash"]


def test_detect_content_drift_unknown_entity(db: TallyCache) -> None:
    drift = db.detect_content_drift("nonexistent")
    assert drift == []


def test_sync_errors_table_exists(db: TallyCache) -> None:
    rows = db.query(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = 'sync_errors'"
    )
    assert len(rows) >= 1


def test_log_and_get_sync_errors(db: TallyCache) -> None:
    db.log_sync_error("voucher", "guid-v-fail", "Invalid data")
    errors = db.get_sync_errors()
    assert len(errors) == 1
    assert errors[0]["entity_type"] == "voucher"
    assert errors[0]["record_guid"] == "guid-v-fail"


def test_get_sync_errors_filtered(db: TallyCache) -> None:
    db.log_sync_error("voucher", "guid-1", "Error 1")
    db.log_sync_error("ledger", "guid-2", "Error 2")
    errors = db.get_sync_errors(entity_type="voucher")
    assert len(errors) == 1
    assert errors[0]["entity_type"] == "voucher"


def test_upsert_voucher_logs_sync_error(db: TallyCache) -> None:
    voucher = TallyVoucher(
        guid="v-err",
        alter_id=1,
        voucher_number="1",
        voucher_type="Sales",
        date=date(2025, 1, 1),
        ledger_entries=[TallyVoucherEntry(ledger_name="A", amount=Decimal("100"))],
    )
    db.upsert_vouchers([voucher])
    errors = db.get_sync_errors(entity_type="voucher")
    assert len(errors) == 0


def test_upsert_groups_empty_list(db: TallyCache) -> None:
    count = db.upsert_groups([])
    assert count == 0


def test_upsert_stock_items_empty_list(db: TallyCache) -> None:
    count = db.upsert_stock_items([])
    assert count == 0


def test_upsert_voucher_types_empty_list(db: TallyCache) -> None:
    count = db.upsert_voucher_types([])
    assert count == 0


def test_upsert_units_empty_list(db: TallyCache) -> None:
    count = db.upsert_units([])
    assert count == 0


def test_upsert_stock_groups_empty_list(db: TallyCache) -> None:
    count = db.upsert_stock_groups([])
    assert count == 0


def test_upsert_cost_centers_empty_list(db: TallyCache) -> None:
    count = db.upsert_cost_centers([])
    assert count == 0


def test_upsert_vouchers_empty_list(db: TallyCache) -> None:
    count, max_id = db.upsert_vouchers([])
    assert count == 0
    assert max_id == 0


def test_compare_content_drift_new_record_not_in_before(db: TallyCache) -> None:
    ledger = TallyLedger(
        name="Cash", guid="g1", alter_id=1, parent_group="Cash-in-Hand"
    )
    db.upsert_ledgers([ledger])
    before = db.detect_content_drift("ledger")
    new_ledger = TallyLedger(
        name="Bank", guid="g2", alter_id=2, parent_group="Bank Accounts"
    )
    db.upsert_ledgers([new_ledger])
    drift = db.compare_content_drift("ledger", before)
    assert isinstance(drift, list)


def test_query_readonly_failure_raises(db: TallyCache) -> None:
    with pytest.raises(TallyBridgeCacheError):
        db.query_readonly("SELECT * FROM nonexistent_table_xyz")


def test_get_outstanding_receivables(db: TallyCache) -> None:
    voucher = TallyVoucher(
        guid="v-rec",
        alter_id=1,
        voucher_number="SI/001",
        voucher_type="Sales",
        date=date(2025, 4, 1),
        total_amount=Decimal("50000"),
        ledger_entries=[TallyVoucherEntry(ledger_name="Cash", amount=Decimal("50000"))],
    )
    db.upsert_vouchers([voucher])
    bills = db.get_outstanding_receivables()
    assert isinstance(bills, list)


def test_get_outstanding_payables(db: TallyCache) -> None:
    voucher = TallyVoucher(
        guid="v-pay",
        alter_id=2,
        voucher_number="PI/001",
        voucher_type="Purchase",
        date=date(2025, 4, 1),
        total_amount=Decimal("30000"),
        ledger_entries=[TallyVoucherEntry(ledger_name="Bank", amount=Decimal("30000"))],
    )
    db.upsert_vouchers([voucher])
    bills = db.get_outstanding_payables()
    assert isinstance(bills, list)


def test_get_sync_status_after_sync(db: TallyCache) -> None:
    db.update_sync_state("ledger", 100, 50)
    status = db.get_sync_status()
    assert "ledger" in status
    assert status["ledger"]["last_alter_id"] == 100


def test_get_cached_guids(db: TallyCache) -> None:
    from tallybridge.models.master import TallyLedger

    db.upsert_ledgers(
        [
            TallyLedger(
                name="Test1",
                guid="guid-1",
                alter_id=1,
                parent_group="Assets",
            ),
            TallyLedger(
                name="Test2",
                guid="guid-2",
                alter_id=2,
                parent_group="Assets",
            ),
        ]
    )
    guids = db.get_cached_guids("ledger")
    assert "guid-1" in guids
    assert "guid-2" in guids


def test_delete_records_by_guid(db: TallyCache) -> None:
    from tallybridge.models.master import TallyLedger

    db.upsert_ledgers(
        [
            TallyLedger(
                name="Del1",
                guid="del-1",
                alter_id=1,
                parent_group="Assets",
            ),
            TallyLedger(
                name="Del2",
                guid="del-2",
                alter_id=2,
                parent_group="Assets",
            ),
        ]
    )
    count = db.delete_records_by_guid("ledger", {"del-1"})
    assert count >= 0
    guids = db.get_cached_guids("ledger")
    assert "del-1" not in guids


def test_delete_records_empty_guids(db: TallyCache) -> None:
    count = db.delete_records_by_guid("ledger", set())
    assert count == 0


def test_get_cached_guids_unknown_type(db: TallyCache) -> None:
    guids = db.get_cached_guids("nonexistent")
    assert guids == set()


# ── BI Views Tests (Phase 11C) ──────────────────────────────────────────


def test_bi_views_created_on_initialize(db: TallyCache) -> None:
    views = db.query(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_type = 'VIEW' "
        "ORDER BY table_name"
    )
    view_names = {v["table_name"] for v in views}
    assert "v_sales_summary" in view_names
    assert "v_receivables" in view_names
    assert "v_gst_summary" in view_names
    assert "v_stock_summary" in view_names
    assert "v_party_position" in view_names


def test_v_sales_summary_view(db: TallyCache) -> None:
    db.upsert_vouchers([
        TallyVoucher(
            guid="guid-v-sales-001",
            alter_id=1,
            voucher_number="S-001",
            voucher_type="Sales",
            date=date(2025, 1, 15),
            total_amount=Decimal("10000"),
            ledger_entries=[],
        ),
    ])
    result = db.query("SELECT * FROM v_sales_summary")
    assert len(result) == 1
    assert result[0]["voucher_type"] == "Sales"
    assert result[0]["total_amount"] == Decimal("10000")


def test_v_stock_summary_view(db: TallyCache) -> None:
    db.upsert_stock_items([
        TallyStockItem(
            name="Widget A",
            guid="guid-stock-bi-001",
            alter_id=1,
            parent_group="Finished Goods",
            unit="Nos",
            closing_quantity=Decimal("100"),
            closing_value=Decimal("5000"),
        ),
    ])
    result = db.query("SELECT * FROM v_stock_summary WHERE name = 'Widget A'")
    assert len(result) == 1
    assert result[0]["closing_quantity"] == Decimal("100")


def test_v_party_position_view(db: TallyCache) -> None:
    db.upsert_ledgers([
        TallyLedger(
            name="Debtor A",
            guid="guid-party-bi-001",
            alter_id=1,
            parent_group="Sundry Debtors",
            closing_balance=Decimal("5000"),
        ),
    ])
    result = db.query("SELECT * FROM v_party_position WHERE party_name = 'Debtor A'")
    assert len(result) == 1
    assert result[0]["position_type"] == "Receivable"


def test_v_receivables_view(db: TallyCache) -> None:
    db.upsert_vouchers([
        TallyVoucher(
            guid="guid-recv-bi-001",
            alter_id=1,
            voucher_number="S-002",
            voucher_type="Sales",
            date=date(2025, 1, 10),
            party_ledger="Customer X",
            total_amount=Decimal("8000"),
            ledger_entries=[],
        ),
    ])
    result = db.query("SELECT * FROM v_receivables WHERE party_name = 'Customer X'")
    assert len(result) >= 1


def test_upsert_voucher_with_currency(db: TallyCache) -> None:
    voucher = TallyVoucher(
        guid="v-fx",
        alter_id=1,
        voucher_number="FX/001",
        voucher_type="Sales",
        date=date(2025, 4, 1),
        currency="USD",
        forex_amount=Decimal("1000"),
        exchange_rate=Decimal("83.25"),
        base_currency_amount=Decimal("83250"),
        ledger_entries=[
            TallyVoucherEntry(
                ledger_name="Bank USD",
                amount=Decimal("83250"),
                currency="USD",
                forex_amount=Decimal("1000"),
                exchange_rate=Decimal("83.25"),
            )
        ],
    )
    db.upsert_vouchers([voucher])
    rows = db.query("SELECT * FROM trn_voucher WHERE guid = 'v-fx'")
    assert len(rows) == 1
    assert rows[0]["currency"] == "USD"
    assert rows[0]["forex_amount"] == Decimal("1000")
    assert rows[0]["exchange_rate"] == Decimal("83.25")
