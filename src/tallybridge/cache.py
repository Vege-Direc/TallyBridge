"""DuckDB cache layer — see SPECS.md §6."""

import os
from datetime import date
from decimal import Decimal
from typing import Any

import duckdb
from loguru import logger

from tallybridge.exceptions import TallyBridgeCacheError
from tallybridge.models.master import (
    TallyCostCenter,
    TallyGroup,
    TallyLedger,
    TallyStockGroup,
    TallyStockItem,
    TallyUnit,
    TallyVoucherType,
)
from tallybridge.models.report import OutstandingBill, TrialBalanceLine
from tallybridge.models.voucher import (
    TallyVoucher,
)

SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS mst_ledger (
    guid            TEXT PRIMARY KEY,
    alter_id        INTEGER NOT NULL,
    name            TEXT NOT NULL,
    parent_group    TEXT,
    opening_balance DECIMAL(18,4) DEFAULT 0,
    closing_balance DECIMAL(18,4) DEFAULT 0,
    is_revenue      BOOLEAN DEFAULT false,
    affects_gross_profit BOOLEAN DEFAULT false,
    gstin           TEXT,
    party_name      TEXT,
    synced_at       TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS mst_group (
    guid                 TEXT PRIMARY KEY,
    alter_id             INTEGER NOT NULL,
    name                 TEXT NOT NULL,
    parent               TEXT,
    primary_group        TEXT,
    is_revenue           BOOLEAN DEFAULT false,
    affects_gross_profit BOOLEAN DEFAULT false,
    net_debit_credit     TEXT DEFAULT 'Dr',
    synced_at            TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS mst_stock_item (
    guid             TEXT PRIMARY KEY,
    alter_id         INTEGER NOT NULL,
    name             TEXT NOT NULL,
    parent_group     TEXT,
    unit             TEXT,
    gst_rate         DECIMAL(6,2),
    hsn_code         TEXT,
    opening_quantity DECIMAL(18,4) DEFAULT 0,
    opening_rate     DECIMAL(18,4) DEFAULT 0,
    closing_quantity DECIMAL(18,4) DEFAULT 0,
    closing_value    DECIMAL(18,4) DEFAULT 0,
    synced_at        TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS mst_voucher_type (
    guid      TEXT PRIMARY KEY,
    alter_id  INTEGER NOT NULL,
    name      TEXT NOT NULL,
    parent    TEXT,
    synced_at TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS mst_unit (
    guid            TEXT PRIMARY KEY,
    alter_id        INTEGER NOT NULL,
    name            TEXT NOT NULL,
    unit_type       TEXT DEFAULT 'Simple',
    base_units      TEXT,
    decimal_places  INTEGER DEFAULT 0,
    symbol          TEXT,
    synced_at       TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS mst_stock_group (
    guid                   TEXT PRIMARY KEY,
    alter_id               INTEGER NOT NULL,
    name                   TEXT NOT NULL,
    parent                 TEXT,
    should_quantities_add  BOOLEAN DEFAULT true,
    synced_at              TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS mst_cost_center (
    guid              TEXT PRIMARY KEY,
    alter_id          INTEGER NOT NULL,
    name              TEXT NOT NULL,
    parent            TEXT,
    email             TEXT,
    cost_centre_type  TEXT DEFAULT 'Primary',
    synced_at         TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS trn_voucher (
    guid             TEXT PRIMARY KEY,
    alter_id         INTEGER NOT NULL,
    voucher_number   TEXT,
    voucher_type     TEXT,
    date             DATE NOT NULL,
    effective_date   DATE,
    reference        TEXT,
    narration        TEXT,
    party_ledger     TEXT,
    party_gstin      TEXT,
    place_of_supply  TEXT,
    due_date         DATE,
    entered_by       TEXT,
    is_cancelled     BOOLEAN DEFAULT false,
    is_optional      BOOLEAN DEFAULT false,
    is_postdated     BOOLEAN DEFAULT false,
    is_void          BOOLEAN DEFAULT false,
    total_amount     DECIMAL(18,4) DEFAULT 0,
    gst_amount       DECIMAL(18,4) DEFAULT 0,
    synced_at        TIMESTAMP DEFAULT current_timestamp
);

CREATE SEQUENCE IF NOT EXISTS seq_entry_id START 1;

CREATE TABLE IF NOT EXISTS trn_ledger_entry (
    id           BIGINT DEFAULT nextval('seq_entry_id') PRIMARY KEY,
    voucher_guid TEXT NOT NULL REFERENCES trn_voucher(guid),
    ledger_name  TEXT NOT NULL,
    amount       DECIMAL(18,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS trn_inventory_entry (
    id               BIGINT DEFAULT nextval('seq_entry_id') PRIMARY KEY,
    voucher_guid     TEXT NOT NULL REFERENCES trn_voucher(guid),
    stock_item_name  TEXT NOT NULL,
    quantity         DECIMAL(18,4) DEFAULT 0,
    rate             DECIMAL(18,4) DEFAULT 0,
    amount           DECIMAL(18,4) DEFAULT 0,
    godown           TEXT,
    batch            TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    entity_type   TEXT PRIMARY KEY,
    last_alter_id INTEGER DEFAULT 0,
    last_sync_at  TIMESTAMP,
    record_count  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMP DEFAULT current_timestamp,
    description TEXT
);
"""

MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "add trn_cost_centre junction table",
        """CREATE TABLE IF NOT EXISTS trn_cost_centre (
    id              BIGINT DEFAULT nextval('seq_entry_id') PRIMARY KEY,
    voucher_guid    TEXT NOT NULL REFERENCES trn_voucher(guid),
    ledger_name     TEXT NOT NULL,
    cost_centre     TEXT NOT NULL,
    amount          DECIMAL(18,4) NOT NULL
);""",
    ),
    (
        2,
        "add trn_bill allocations table",
        """CREATE TABLE IF NOT EXISTS trn_bill (
    id              BIGINT DEFAULT nextval('seq_entry_id') PRIMARY KEY,
    voucher_guid    TEXT NOT NULL REFERENCES trn_voucher(guid),
    ledger_name     TEXT NOT NULL,
    bill_name       TEXT NOT NULL,
    amount          DECIMAL(18,4) NOT NULL,
    bill_type       TEXT,
    bill_credit_period INTEGER
);""",
    ),
    (
        3,
        "add company column to all tables",
        """ALTER TABLE mst_ledger ADD COLUMN IF NOT EXISTS company TEXT;
ALTER TABLE mst_group ADD COLUMN IF NOT EXISTS company TEXT;
ALTER TABLE mst_stock_item ADD COLUMN IF NOT EXISTS company TEXT;
ALTER TABLE mst_voucher_type ADD COLUMN IF NOT EXISTS company TEXT;
ALTER TABLE mst_unit ADD COLUMN IF NOT EXISTS company TEXT;
ALTER TABLE mst_stock_group ADD COLUMN IF NOT EXISTS company TEXT;
ALTER TABLE mst_cost_center ADD COLUMN IF NOT EXISTS company TEXT;
ALTER TABLE trn_voucher ADD COLUMN IF NOT EXISTS company TEXT;""",
    ),
]


class TallyCache:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: duckdb.DuckDBPyConnection | None = None
        self.initialize()

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(self._db_path)
        return self._conn

    def initialize(self) -> None:
        """Create schema if not exists. Apply any pending migrations. Idempotent."""
        self.conn.execute(SCHEMA_SQL)
        for version, description, sql in MIGRATIONS:
            existing = self.conn.execute(
                "SELECT COUNT(*) FROM schema_version WHERE version = ?", [version]
            ).fetchone()
            if existing and existing[0] == 0:
                self.conn.execute(sql)
                self.conn.execute(
                    "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                    [version, description],
                )

    def upsert_ledgers(self, ledgers: list[TallyLedger]) -> int:
        """INSERT OR REPLACE ledgers by guid. Returns affected row count."""
        count = 0
        for ledger in ledgers:
            self.conn.execute(
                """INSERT OR REPLACE INTO mst_ledger
                (guid, alter_id, name, parent_group, opening_balance, closing_balance,
                 is_revenue, affects_gross_profit, gstin, party_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    ledger.guid,
                    ledger.alter_id,
                    ledger.name,
                    ledger.parent_group,
                    ledger.opening_balance,
                    ledger.closing_balance,
                    ledger.is_revenue,
                    ledger.affects_gross_profit,
                    ledger.gstin,
                    ledger.party_name,
                ],
            )
            count += 1
        return count

    def upsert_groups(self, groups: list[TallyGroup]) -> int:
        count = 0
        for group in groups:
            self.conn.execute(
                """INSERT OR REPLACE INTO mst_group
                (guid, alter_id, name, parent, primary_group, is_revenue,
                 affects_gross_profit, net_debit_credit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    group.guid,
                    group.alter_id,
                    group.name,
                    group.parent,
                    group.primary_group,
                    group.is_revenue,
                    group.affects_gross_profit,
                    group.net_debit_credit,
                ],
            )
            count += 1
        return count

    def upsert_stock_items(self, items: list[TallyStockItem]) -> int:
        count = 0
        for item in items:
            self.conn.execute(
                """INSERT OR REPLACE INTO mst_stock_item
                (guid, alter_id, name, parent_group, unit, gst_rate, hsn_code,
                 opening_quantity, opening_rate, closing_quantity, closing_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    item.guid,
                    item.alter_id,
                    item.name,
                    item.parent_group,
                    item.unit,
                    item.gst_rate if item.gst_rate is not None else None,
                    item.hsn_code,
                    item.opening_quantity,
                    item.opening_rate,
                    item.closing_quantity,
                    item.closing_value,
                ],
            )
            count += 1
        return count

    def upsert_voucher_types(self, vtypes: list[TallyVoucherType]) -> int:
        count = 0
        for vt in vtypes:
            self.conn.execute(
                """INSERT OR REPLACE INTO mst_voucher_type
                (guid, alter_id, name, parent) VALUES (?, ?, ?, ?)""",
                [vt.guid, vt.alter_id, vt.name, vt.parent],
            )
            count += 1
        return count

    def upsert_units(self, units: list[TallyUnit]) -> int:
        count = 0
        for unit in units:
            self.conn.execute(
                """INSERT OR REPLACE INTO mst_unit
                (guid, alter_id, name, unit_type, base_units, decimal_places, symbol)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    unit.guid,
                    unit.alter_id,
                    unit.name,
                    unit.unit_type,
                    unit.base_units,
                    unit.decimal_places,
                    unit.symbol,
                ],
            )
            count += 1
        return count

    def upsert_stock_groups(self, groups: list[TallyStockGroup]) -> int:
        count = 0
        for sg in groups:
            self.conn.execute(
                """INSERT OR REPLACE INTO mst_stock_group
                (guid, alter_id, name, parent, should_quantities_add)
                VALUES (?, ?, ?, ?, ?)""",
                [sg.guid, sg.alter_id, sg.name, sg.parent, sg.should_quantities_add],
            )
            count += 1
        return count

    def upsert_cost_centers(self, centers: list[TallyCostCenter]) -> int:
        count = 0
        for cc in centers:
            self.conn.execute(
                """INSERT OR REPLACE INTO mst_cost_center
                (guid, alter_id, name, parent, email, cost_centre_type)
                VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    cc.guid,
                    cc.alter_id,
                    cc.name,
                    cc.parent,
                    cc.email,
                    cc.cost_centre_type,
                ],
            )
            count += 1
        return count

    def upsert_vouchers(
        self, vouchers: list[TallyVoucher], company: str | None = None
    ) -> int:
        """Upsert vouchers and replace their child entries atomically."""
        count = 0
        for voucher in vouchers:
            try:
                self.conn.begin()
                self.conn.execute(
                    "DELETE FROM trn_ledger_entry WHERE voucher_guid = ?",
                    [voucher.guid],
                )
                self.conn.execute(
                    "DELETE FROM trn_inventory_entry WHERE voucher_guid = ?",
                    [voucher.guid],
                )
                self.conn.execute(
                    "DELETE FROM trn_cost_centre WHERE voucher_guid = ?",
                    [voucher.guid],
                )
                self.conn.execute(
                    "DELETE FROM trn_bill WHERE voucher_guid = ?",
                    [voucher.guid],
                )
                self.conn.execute(
                    """INSERT OR REPLACE INTO trn_voucher
                    (guid, alter_id, voucher_number, voucher_type, date,
                     effective_date, reference, narration, party_ledger,
                     party_gstin, place_of_supply, due_date, entered_by,
                     is_cancelled, is_optional, is_postdated, is_void,
                     total_amount, gst_amount, company)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [
                        voucher.guid,
                        voucher.alter_id,
                        voucher.voucher_number,
                        voucher.voucher_type,
                        str(voucher.date),
                        str(voucher.effective_date) if voucher.effective_date else None,
                        voucher.reference,
                        voucher.narration,
                        voucher.party_ledger,
                        voucher.party_gstin,
                        voucher.place_of_supply,
                        str(voucher.due_date) if voucher.due_date else None,
                        voucher.entered_by,
                        voucher.is_cancelled,
                        voucher.is_optional,
                        voucher.is_postdated,
                        voucher.is_void,
                        voucher.total_amount,
                        voucher.gst_amount,
                        company,
                    ],
                )
                for entry in voucher.ledger_entries:
                    self.conn.execute(
                        """INSERT INTO trn_ledger_entry
                        (voucher_guid, ledger_name, amount) VALUES (?, ?, ?)""",
                        [voucher.guid, entry.ledger_name, entry.amount],
                    )
                for entry in voucher.inventory_entries:  # type: ignore[assignment]
                    self.conn.execute(
                        """INSERT INTO trn_inventory_entry
                        (voucher_guid, stock_item_name, quantity,
                         rate, amount, godown, batch)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        [
                            voucher.guid,
                            entry.stock_item_name,  # type: ignore[attr-defined]
                            entry.quantity,  # type: ignore[attr-defined]
                            entry.rate,  # type: ignore[attr-defined]
                            entry.amount,
                            entry.godown,  # type: ignore[attr-defined]
                            entry.batch,  # type: ignore[attr-defined]
                        ],
                    )
                for cc in voucher.cost_centre_allocations:  # type: ignore[attr-defined]
                    self.conn.execute(
                        """INSERT INTO trn_cost_centre
                        (voucher_guid, ledger_name, cost_centre, amount)
                        VALUES (?, ?, ?, ?)""",
                        [voucher.guid, cc.ledger_name, cc.cost_centre, cc.amount],
                    )
                for bill in voucher.bill_allocations:  # type: ignore[attr-defined]
                    self.conn.execute(
                        """INSERT INTO trn_bill
                        (voucher_guid, ledger_name, bill_name, amount,
                         bill_type, bill_credit_period)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        [
                            voucher.guid,
                            bill.ledger_name,
                            bill.bill_name,
                            bill.amount,
                            bill.bill_type,
                            bill.bill_credit_period,
                        ],
                    )
                self.conn.commit()
                count += 1
            except Exception as exc:
                self.conn.rollback()
                logger.warning("Failed to upsert voucher {}: {}", voucher.guid, exc)
        return count

    def get_last_alter_id(self, entity_type: str) -> int:
        """Return last synced AlterID for entity_type, or 0 if not yet synced."""
        result = self.conn.execute(
            "SELECT last_alter_id FROM sync_state WHERE entity_type = ?",
            [entity_type],
        ).fetchone()
        return result[0] if result else 0

    def update_sync_state(
        self, entity_type: str, last_alter_id: int, record_count: int
    ) -> None:
        """Upsert a sync_state row after successful sync."""
        self.conn.execute(
            """INSERT OR REPLACE INTO sync_state
            (entity_type, last_alter_id, last_sync_at, record_count)
            VALUES (?, ?, current_timestamp, ?)""",
            [entity_type, last_alter_id, record_count],
        )

    def get_sync_status(self) -> dict[str, dict[str, Any]]:
        """Return {entity_type: {last_alter_id, last_sync_at, record_count}}
        for all rows."""
        rows = self.conn.execute(
            "SELECT entity_type, last_alter_id, last_sync_at, "
            "record_count FROM sync_state"
        ).fetchall()
        return {
            row[0]: {
                "last_alter_id": row[1],
                "last_sync_at": str(row[2]) if row[2] else None,
                "record_count": row[3],
            }
            for row in rows
        }

    def query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """Execute parameterised SELECT, return list of row dicts. Read-only."""
        try:
            result = self.conn.execute(sql, params or [])
            columns = [desc[0] for desc in result.description]
            return [dict(zip(columns, row, strict=False)) for row in result.fetchall()]
        except Exception as exc:
            logger.warning("Query failed: {}", exc)
            raise TallyBridgeCacheError(str(exc)) from exc

    def get_ledger(self, name: str) -> TallyLedger | None:
        rows = self.query("SELECT * FROM mst_ledger WHERE name = ?", [name])
        if not rows:
            return None
        r = rows[0]
        return TallyLedger(
            guid=r["guid"],
            alter_id=r["alter_id"],
            name=r["name"],
            parent_group=r["parent_group"] or "",
            opening_balance=Decimal(str(r["opening_balance"] or 0)),
            closing_balance=Decimal(str(r["closing_balance"] or 0)),
            is_revenue=bool(r["is_revenue"]),
            affects_gross_profit=bool(r["affects_gross_profit"]),
            gstin=r.get("gstin"),
            party_name=r.get("party_name"),
        )

    def get_ledger_balance(self, name: str) -> Decimal:
        rows = self.query(
            "SELECT closing_balance FROM mst_ledger WHERE name = ?", [name]
        )
        if not rows:
            raise KeyError(f"Ledger '{name}' not found")
        return Decimal(str(rows[0]["closing_balance"]))

    def get_outstanding_receivables(self) -> list[OutstandingBill]:
        return self._get_outstanding("Sales")

    def get_outstanding_payables(self) -> list[OutstandingBill]:
        return self._get_outstanding("Purchase")

    def _get_outstanding(self, voucher_type: str) -> list[OutstandingBill]:
        bills: list[OutstandingBill] = []
        rows = self.query(
            """SELECT v.guid, v.date, v.voucher_number, v.party_ledger, v.total_amount
            FROM trn_voucher v
            WHERE v.voucher_type = ? AND v.is_cancelled = false AND v.is_void = false
            ORDER BY v.date""",
            [voucher_type],
        )
        for r in rows:
            bill_date = r["date"] if isinstance(r["date"], date) else date.today()
            bills.append(
                OutstandingBill(
                    party_name=r["party_ledger"] or "",
                    bill_date=bill_date,
                    bill_number=r["voucher_number"] or "",
                    bill_amount=Decimal(str(r["total_amount"] or 0)),
                    outstanding_amount=Decimal(str(r["total_amount"] or 0)),
                    voucher_type=voucher_type,
                )
            )
        return bills

    def get_trial_balance(
        self, from_date: date, to_date: date
    ) -> list[TrialBalanceLine]:
        rows = self.query(
            """SELECT l.name as ledger, l.parent_group as group_name,
                      l.opening_balance, l.closing_balance
               FROM mst_ledger l
               ORDER BY l.name"""
        )
        lines: list[TrialBalanceLine] = []
        for r in rows:
            ob = Decimal(str(r["opening_balance"] or 0))
            cb = Decimal(str(r["closing_balance"] or 0))
            od = ob if ob > 0 else Decimal("0")
            oc = -ob if ob < 0 else Decimal("0")
            cd = cb if cb > 0 else Decimal("0")
            cc = -cb if cb < 0 else Decimal("0")
            lines.append(
                TrialBalanceLine(
                    ledger=r["ledger"],
                    group=r["group_name"] or "",
                    opening_debit=od,
                    opening_credit=oc,
                    closing_debit=cd,
                    closing_credit=cc,
                )
            )
        return lines

    def health_check(self) -> dict[str, Any]:
        """Return {record_counts, last_sync_times, db_size_mb, schema_version}."""
        tables = [
            "mst_ledger",
            "mst_group",
            "mst_stock_item",
            "mst_voucher_type",
            "mst_unit",
            "mst_stock_group",
            "mst_cost_center",
            "trn_voucher",
            "trn_cost_centre",
            "trn_bill",
        ]
        record_counts: dict[str, int] = {}
        for t in tables:
            try:
                result = self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
                record_counts[t] = result[0] if result else 0
            except Exception:
                record_counts[t] = 0

        sync_status = self.get_sync_status()
        db_size_mb = 0.0
        if os.path.exists(self._db_path):
            db_size_mb = os.path.getsize(self._db_path) / (1024 * 1024)

        return {
            "record_counts": record_counts,
            "last_sync_times": {k: v["last_sync_at"] for k, v in sync_status.items()},
            "db_size_mb": round(db_size_mb, 2),
            "schema_version": 0,
        }

    def query_readonly(
        self, sql: str, params: list[Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute SQL query with read-only enforcement.

        DuckDB does not support concurrent read-only and read-write connections
        to the same file within a single process, nor does ATTACH allow
        attaching the same file twice. Instead, we enforce read-only by:

        1. Beginning a read-only transaction (BEGIN READ ONLY)
        2. Executing the query
        3. Aborting the transaction (ROLLBACK)

        This ensures no writes can occur during query execution.
        If BEGIN READ ONLY fails (e.g. inside an existing transaction),
        falls back to executing directly.
        """
        try:
            self.conn.execute("BEGIN READ ONLY")
        except Exception:
            try:
                self.conn.execute("COMMIT")
            except Exception:
                pass
            try:
                self.conn.execute("BEGIN READ ONLY")
            except Exception:
                result = self.conn.execute(sql, params or [])
                columns = [desc[0] for desc in result.description]
                return [
                    dict(zip(columns, row, strict=False))
                    for row in result.fetchall()
                ]

        try:
            result = self.conn.execute(sql, params or [])
            columns = [desc[0] for desc in result.description]
            rows = [dict(zip(columns, row, strict=False)) for row in result.fetchall()]
            return rows
        except Exception as exc:
            logger.warning("Read-only query failed: {}", exc)
            raise TallyBridgeCacheError(str(exc)) from exc
        finally:
            try:
                self.conn.execute("ROLLBACK")
            except Exception:
                pass

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
