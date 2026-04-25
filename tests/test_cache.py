"""Tests for cache — SPECS.md §6."""

from datetime import date
from decimal import Decimal

import pytest

from tallybridge.cache import TallyCache
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
    ledger = TallyLedger(name="Cash", guid="g1", alter_id=1, parent_group="Cash-in-Hand")
    count = db.upsert_ledgers([ledger])
    assert count == 1
    rows = db.query("SELECT COUNT(*) as cnt FROM mst_ledger")
    assert rows[0]["cnt"] == 1


def test_upsert_ledgers_updates(db: TallyCache) -> None:
    ledger = TallyLedger(name="Cash", guid="g1", alter_id=1, parent_group="Cash-in-Hand")
    db.upsert_ledgers([ledger])
    updated = TallyLedger(name="Cash", guid="g1", alter_id=2, parent_group="Cash-in-Hand")
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
    assert count == 1
    v_rows = db.query("SELECT COUNT(*) as cnt FROM trn_voucher")
    assert v_rows[0]["cnt"] == 1
    le_rows = db.query("SELECT COUNT(*) as cnt FROM trn_ledger_entry")
    assert le_rows[0]["cnt"] == 1
    ie_rows = db.query("SELECT COUNT(*) as cnt FROM trn_inventory_entry")
    assert ie_rows[0]["cnt"] == 1


def test_upsert_vouchers_replaces_entries(db: TallyCache) -> None:
    v1 = TallyVoucher(
        guid="v1", alter_id=1, voucher_number="1", voucher_type="Sales",
        date=date(2025, 1, 1),
        ledger_entries=[TallyVoucherEntry(ledger_name="A", amount=Decimal("100"))],
    )
    db.upsert_vouchers([v1])
    v2 = TallyVoucher(
        guid="v1", alter_id=2, voucher_number="1", voucher_type="Sales",
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
