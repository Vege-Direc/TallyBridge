"""DuckDB cache layer — see SPECS.md §6."""

import hashlib
import os
from datetime import date
from decimal import Decimal
from typing import Any

import duckdb
from loguru import logger

from tallybridge.exceptions import TallyBridgeCacheError
from tallybridge.models.master import (
    TallyCostCenter,
    TallyGodown,
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

CREATE TABLE IF NOT EXISTS mst_godown (
    guid       TEXT PRIMARY KEY,
    alter_id   INTEGER NOT NULL,
    name       TEXT NOT NULL,
    parent     TEXT,
    synced_at  TIMESTAMP DEFAULT current_timestamp
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
    (
        4,
        "add content_hash column to master tables for drift detection",
        """ALTER TABLE mst_ledger ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE mst_group ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE mst_stock_item ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE mst_voucher_type ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE mst_unit ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE mst_stock_group ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE mst_cost_center ADD COLUMN IF NOT EXISTS content_hash TEXT;""",
    ),
    (
        5,
        "add sync_errors table for tracking failed records",
        """CREATE TABLE IF NOT EXISTS sync_errors (
    id          BIGINT DEFAULT nextval('seq_entry_id') PRIMARY KEY,
    entity_type TEXT NOT NULL,
    record_guid TEXT,
    error_message TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT current_timestamp
);""",
    ),
    (
        6,
        "add company and content_hash columns to mst_godown",
        """ALTER TABLE mst_godown ADD COLUMN IF NOT EXISTS company TEXT;
ALTER TABLE mst_godown ADD COLUMN IF NOT EXISTS content_hash TEXT;""",
    ),
    (
        7,
        "add currency fields to trn_voucher",
        """ALTER TABLE trn_voucher ADD COLUMN IF NOT EXISTS currency TEXT;
ALTER TABLE trn_voucher ADD COLUMN IF NOT EXISTS forex_amount DECIMAL(18,4);
ALTER TABLE trn_voucher ADD COLUMN IF NOT EXISTS exchange_rate DECIMAL(18,4);
ALTER TABLE trn_voucher ADD COLUMN IF NOT EXISTS base_currency_amount DECIMAL(18,4);""",
    ),
]

VIEWS_SQL = """
CREATE OR REPLACE VIEW v_sales_summary AS
SELECT
    v.voucher_type,
    v.date,
    v.party_ledger,
    v.total_amount,
    v.gst_amount,
    v.voucher_number,
    v.narration,
    v.company
FROM trn_voucher v
WHERE v.voucher_type IN ('Sales', 'Credit Note')
  AND v.is_cancelled = false
  AND v.is_void = false;

CREATE OR REPLACE VIEW v_receivables AS
SELECT
    b.party_name,
    b.bill_date,
    b.bill_number,
    b.bill_amount,
    b.paid_amount,
    b.outstanding_amount,
    b.overdue_days,
    b.voucher_type
FROM (
    SELECT
        v.party_ledger AS party_name,
        v.date AS bill_date,
        v.voucher_number AS bill_number,
        v.total_amount AS bill_amount,
        CAST(0 AS DECIMAL(18,4)) AS paid_amount,
        v.total_amount AS outstanding_amount,
        CASE
            WHEN v.due_date IS NOT NULL AND v.due_date < CURRENT_DATE
            THEN CURRENT_DATE - v.due_date
            ELSE 0
        END AS overdue_days,
        v.voucher_type
    FROM trn_voucher v
    WHERE v.voucher_type IN ('Sales', 'Credit Note')
      AND v.is_cancelled = false
      AND v.is_void = false
      AND v.total_amount > 0
) b
WHERE b.outstanding_amount > 0;

CREATE OR REPLACE VIEW v_gst_summary AS
SELECT
    le.ledger_name AS gst_ledger,
    v.date,
    SUM(le.amount) AS total_amount,
    v.company
FROM trn_ledger_entry le
JOIN trn_voucher v ON le.voucher_guid = v.guid
WHERE le.ledger_name LIKE 'CGST%'
   OR le.ledger_name LIKE 'SGST%'
   OR le.ledger_name LIKE 'IGST%'
GROUP BY le.ledger_name, v.date, v.company;

CREATE OR REPLACE VIEW v_stock_summary AS
SELECT
    name,
    parent_group,
    unit,
    gst_rate,
    hsn_code,
    closing_quantity,
    closing_value,
    company
FROM mst_stock_item;

CREATE OR REPLACE VIEW v_party_position AS
SELECT
    l.name AS party_name,
    l.parent_group,
    l.closing_balance,
    l.gstin,
    l.company,
    CASE
        WHEN l.parent_group = 'Sundry Debtors' THEN 'Receivable'
        WHEN l.parent_group = 'Sundry Creditors' THEN 'Payable'
        ELSE 'Other'
    END AS position_type
FROM mst_ledger l
WHERE l.parent_group IN ('Sundry Debtors', 'Sundry Creditors');
"""


def _compute_content_hash(*values: Any) -> str:
    """Compute SHA-256 hash from field values for drift detection."""
    payload = "|".join(str(v) for v in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        self.conn.execute(VIEWS_SQL)

    def upsert_ledgers(self, ledgers: list[TallyLedger]) -> int:
        """INSERT OR REPLACE ledgers by guid. Returns affected row count."""
        if not ledgers:
            return 0
        rows = [
            (
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
                _compute_content_hash(
                    ledger.name,
                    ledger.parent_group,
                    ledger.opening_balance,
                    ledger.closing_balance,
                    ledger.is_revenue,
                    ledger.affects_gross_profit,
                    ledger.gstin,
                    ledger.party_name,
                ),
            )
            for ledger in ledgers
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO mst_ledger
            (guid, alter_id, name, parent_group, opening_balance, closing_balance,
             is_revenue, affects_gross_profit, gstin, party_name, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        return len(ledgers)

    def upsert_groups(self, groups: list[TallyGroup]) -> int:
        if not groups:
            return 0
        rows = [
            (
                group.guid,
                group.alter_id,
                group.name,
                group.parent,
                group.primary_group,
                group.is_revenue,
                group.affects_gross_profit,
                group.net_debit_credit,
                _compute_content_hash(
                    group.name,
                    group.parent,
                    group.primary_group,
                    group.is_revenue,
                    group.affects_gross_profit,
                    group.net_debit_credit,
                ),
            )
            for group in groups
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO mst_group
            (guid, alter_id, name, parent, primary_group, is_revenue,
             affects_gross_profit, net_debit_credit, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        return len(groups)

    def upsert_stock_items(self, items: list[TallyStockItem]) -> int:
        if not items:
            return 0
        rows = [
            (
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
                _compute_content_hash(
                    item.name,
                    item.parent_group,
                    item.unit,
                    item.gst_rate,
                    item.hsn_code,
                    item.opening_quantity,
                    item.opening_rate,
                    item.closing_quantity,
                    item.closing_value,
                ),
            )
            for item in items
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO mst_stock_item
            (guid, alter_id, name, parent_group, unit, gst_rate, hsn_code,
             opening_quantity, opening_rate, closing_quantity, closing_value,
             content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        return len(items)

    def upsert_voucher_types(self, vtypes: list[TallyVoucherType]) -> int:
        if not vtypes:
            return 0
        rows = [
            (
                vt.guid,
                vt.alter_id,
                vt.name,
                vt.parent,
                _compute_content_hash(vt.name, vt.parent),
            )
            for vt in vtypes
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO mst_voucher_type
            (guid, alter_id, name, parent, content_hash) VALUES (?, ?, ?, ?, ?)""",
            rows,
        )
        return len(vtypes)

    def upsert_units(self, units: list[TallyUnit]) -> int:
        if not units:
            return 0
        rows = [
            (
                unit.guid,
                unit.alter_id,
                unit.name,
                unit.unit_type,
                unit.base_units,
                unit.decimal_places,
                unit.symbol,
                _compute_content_hash(
                    unit.name,
                    unit.unit_type,
                    unit.base_units,
                    unit.decimal_places,
                    unit.symbol,
                ),
            )
            for unit in units
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO mst_unit
            (guid, alter_id, name, unit_type, base_units, decimal_places,
             symbol, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        return len(units)

    def upsert_stock_groups(self, groups: list[TallyStockGroup]) -> int:
        if not groups:
            return 0
        rows = [
            (
                sg.guid,
                sg.alter_id,
                sg.name,
                sg.parent,
                sg.should_quantities_add,
                _compute_content_hash(sg.name, sg.parent, sg.should_quantities_add),
            )
            for sg in groups
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO mst_stock_group
            (guid, alter_id, name, parent, should_quantities_add, content_hash)
            VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        return len(groups)

    def upsert_cost_centers(self, centers: list[TallyCostCenter]) -> int:
        if not centers:
            return 0
        rows = [
            (
                cc.guid,
                cc.alter_id,
                cc.name,
                cc.parent,
                cc.email,
                cc.cost_centre_type,
                _compute_content_hash(
                    cc.name, cc.parent, cc.email, cc.cost_centre_type
                ),
            )
            for cc in centers
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO mst_cost_center
            (guid, alter_id, name, parent, email, cost_centre_type, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        return len(centers)

    def upsert_godowns(self, godowns: list[TallyGodown]) -> int:
        if not godowns:
            return 0
        rows = [
            (
                g.guid,
                g.alter_id,
                g.name,
                g.parent,
                _compute_content_hash(g.name, g.parent),
            )
            for g in godowns
        ]
        self.conn.executemany(
            """INSERT OR REPLACE INTO mst_godown
            (guid, alter_id, name, parent, content_hash)
            VALUES (?, ?, ?, ?, ?)""",
            rows,
        )
        return len(godowns)

    def upsert_vouchers(
        self, vouchers: list[TallyVoucher], company: str | None = None
    ) -> tuple[int, int]:
        """Upsert vouchers and replace their child entries atomically.

        Returns (count_committed, max_alter_id_committed) so callers can
        safely advance sync_state only to the highest successfully
        committed alter_id.
        """
        count = 0
        max_committed_alter_id = 0
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
                     total_amount, gst_amount, company, currency,
                     forex_amount, exchange_rate, base_currency_amount)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                        voucher.currency,
                        voucher.forex_amount,
                        voucher.exchange_rate,
                        voucher.base_currency_amount,
                    ],
                )
                for le in voucher.ledger_entries:
                    self.conn.execute(
                        """INSERT INTO trn_ledger_entry
                        (voucher_guid, ledger_name, amount) VALUES (?, ?, ?)""",
                        [voucher.guid, le.ledger_name, le.amount],
                    )
                for ie in voucher.inventory_entries:
                    self.conn.execute(
                        """INSERT INTO trn_inventory_entry
                        (voucher_guid, stock_item_name, quantity,
                         rate, amount, godown, batch)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        [
                            voucher.guid,
                            ie.stock_item_name,
                            ie.quantity,
                            ie.rate,
                            ie.amount,
                            ie.godown,
                            ie.batch,
                        ],
                    )
                for cc in voucher.cost_centre_allocations:
                    self.conn.execute(
                        """INSERT INTO trn_cost_centre
                        (voucher_guid, ledger_name, cost_centre, amount)
                        VALUES (?, ?, ?, ?)""",
                        [voucher.guid, cc.ledger_name, cc.cost_centre, cc.amount],
                    )
                for bill in voucher.bill_allocations:
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
                if voucher.alter_id > max_committed_alter_id:
                    max_committed_alter_id = voucher.alter_id
            except Exception as exc:
                self.conn.rollback()
                logger.warning("Failed to upsert voucher {}: {}", voucher.guid, exc)
                self.log_sync_error("voucher", voucher.guid, str(exc))
        return count, max_committed_alter_id

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
            bill_date = r["date"] if isinstance(r["date"], date) else None
            if bill_date is None:
                logger.warning(
                    "Skipping outstanding bill with missing date: guid={}",
                    r.get("guid"),
                )
                continue
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
        """Return health info: record_counts, last_sync_times, db_size_mb,
        schema_version, orphan_count.
        """
        tables = [
            "mst_ledger",
            "mst_group",
            "mst_stock_item",
            "mst_voucher_type",
            "mst_unit",
            "mst_stock_group",
            "mst_cost_center",
            "mst_godown",
            "trn_voucher",
            "trn_cost_centre",
            "trn_bill",
        ]
        union_parts = " UNION ALL ".join(
            f"SELECT '{t}' as tbl, COUNT(*) as cnt FROM {t}" for t in tables
        )
        record_counts: dict[str, int] = {}
        try:
            rows = self.conn.execute(union_parts).fetchall()
            for row in rows:
                record_counts[row[0]] = row[1]
        except Exception as exc:
            logger.debug("Health check COUNT query failed: {}", exc)
            for t in tables:
                try:
                    result = self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
                    record_counts[t] = result[0] if result else 0
                except Exception:
                    record_counts[t] = 0

        orphan_count = self.reconcile_orphans()

        sync_status = self.get_sync_status()
        db_size_mb = 0.0
        if os.path.exists(self._db_path):
            db_size_mb = os.path.getsize(self._db_path) / (1024 * 1024)

        return {
            "record_counts": record_counts,
            "last_sync_times": {k: v["last_sync_at"] for k, v in sync_status.items()},
            "db_size_mb": round(db_size_mb, 2),
            "schema_version": 0,
            "orphan_count": orphan_count,
        }

    def reconcile_orphans(self) -> int:
        """Detect ledger entries referencing ledgers not in mst_ledger.

        Returns the count of orphaned ledger entries and logs a warning.
        Called from health_check().
        """
        try:
            result = self.conn.execute(
                """SELECT COUNT(*) FROM trn_ledger_entry le
                WHERE NOT EXISTS (
                    SELECT 1 FROM mst_ledger m WHERE m.name = le.ledger_name
                )"""
            ).fetchone()
            orphan_count = result[0] if result else 0
            if orphan_count > 0:
                logger.warning(
                    "Found {} orphaned ledger entries referencing non-existent ledgers",
                    orphan_count,
                )
            return orphan_count
        except Exception as exc:
            logger.debug("Orphan reconciliation failed: {}", exc)
            return 0

    def log_sync_error(
        self, entity_type: str, record_guid: str | None, error_message: str
    ) -> None:
        """Log a failed record to the sync_errors table."""
        try:
            self.conn.execute(
                """INSERT INTO sync_errors (entity_type, record_guid, error_message)
                VALUES (?, ?, ?)""",
                [entity_type, record_guid, error_message],
            )
        except Exception as exc:
            logger.debug("Failed to log sync error: {}", exc)

    def get_sync_errors(
        self, entity_type: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Return recent sync errors, optionally filtered by entity type."""
        if entity_type:
            return self.query(
                """SELECT id, entity_type, record_guid, error_message, created_at
                FROM sync_errors WHERE entity_type = ?
                ORDER BY created_at DESC LIMIT ?""",
                [entity_type, limit],
            )
        return self.query(
            """SELECT id, entity_type, record_guid, error_message, created_at
            FROM sync_errors ORDER BY created_at DESC LIMIT ?""",
            [limit],
        )

    def detect_content_drift(self, entity_type: str) -> list[dict[str, Any]]:
        """Detect records whose content_hash differs from a previous snapshot.

        Takes a snapshot of current content_hash values, which can later be
        compared after a re-sync using compare_content_drift().

        Returns a list of dicts with guid, name, and content_hash for each record.
        """
        hash_configs: dict[str, dict[str, Any]] = {
            "ledger": {"table": "mst_ledger", "name_col": "name"},
            "group": {"table": "mst_group", "name_col": "name"},
            "stock_item": {"table": "mst_stock_item", "name_col": "name"},
            "voucher_type": {"table": "mst_voucher_type", "name_col": "name"},
            "unit": {"table": "mst_unit", "name_col": "name"},
            "stock_group": {"table": "mst_stock_group", "name_col": "name"},
            "cost_center": {"table": "mst_cost_center", "name_col": "name"},
            "godown": {"table": "mst_godown", "name_col": "name"},
        }
        cfg = hash_configs.get(entity_type)
        if cfg is None:
            return []

        table = cfg["table"]
        name_col = cfg["name_col"]
        try:
            rows = self.conn.execute(
                f"SELECT guid, {name_col}, content_hash FROM {table}"
            ).fetchall()
        except Exception as exc:
            logger.debug("Content drift query failed for {}: {}", entity_type, exc)
            return []

        return [
            {
                "entity_type": entity_type,
                "guid": row[0],
                "name": row[1],
                "content_hash": row[2],
            }
            for row in rows
            if row[2] is not None
        ]

    def compare_content_drift(
        self, entity_type: str, before: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Compare current content hashes against a previous snapshot.

        Args:
            entity_type: The entity type to check.
            before: Snapshot from detect_content_drift() taken before re-sync.

        Returns list of dicts for records where the hash changed or was added.
        """
        after = self.detect_content_drift(entity_type)
        before_map = {r["guid"]: r["content_hash"] for r in before}

        drift: list[dict[str, Any]] = []
        for record in after:
            old_hash = before_map.get(record["guid"])
            if old_hash is None:
                continue
            if record["content_hash"] != old_hash:
                drift.append(
                    {
                        "entity_type": entity_type,
                        "guid": record["guid"],
                        "name": record["name"],
                        "old_hash": old_hash,
                        "new_hash": record["content_hash"],
                    }
                )
        if drift:
            logger.warning(
                "Content drift detected for {}: {} record(s) changed",
                entity_type,
                len(drift),
            )
        return drift

    def query_readonly(
        self, sql: str, params: list[Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute SQL query with read-only enforcement.

        Temporarily closes the read-write connection, opens a read-only
        DuckDB connection, executes the query, then reopens read-write.
        This physically prevents all write operations during query execution.
        Never falls back to the read-write connection for queries.
        """
        self._suspend_write_conn()
        try:
            read_conn = duckdb.connect(self._db_path, read_only=True)
            try:
                result = read_conn.execute(sql, params or [])
                columns = [desc[0] for desc in result.description]
                rows = [
                    dict(zip(columns, row, strict=False)) for row in result.fetchall()
                ]

                return rows
            finally:
                read_conn.close()
        except Exception as exc:
            logger.warning("Read-only query failed: {}", exc)
            raise TallyBridgeCacheError(str(exc)) from exc
        finally:
            self._resume_write_conn()

    def _suspend_write_conn(self) -> None:
        """Close the write connection temporarily for read-only access."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _resume_write_conn(self) -> None:
        """Reopen the write connection after read-only access."""
        if self._conn is None:
            self._conn = duckdb.connect(self._db_path)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def get_cached_guids(self, entity_type: str) -> set[str]:
        """Return all GUIDs currently cached for an entity type."""
        table_map: dict[str, str] = {
            "ledger": "mst_ledger",
            "group": "mst_group",
            "stock_item": "mst_stock_item",
            "voucher_type": "mst_voucher_type",
            "unit": "mst_unit",
            "stock_group": "mst_stock_group",
            "cost_center": "mst_cost_center",
            "godown": "mst_godown",
            "voucher": "trn_voucher",
        }
        table = table_map.get(entity_type)
        if table is None or self._conn is None:
            return set()
        try:
            rows = self._conn.execute(f"SELECT guid FROM {table}").fetchall()
            return {str(r[0]) for r in rows if r[0]}
        except Exception as exc:
            logger.warning("Failed to get cached GUIDs for {}: {}", entity_type, exc)
            return set()

    def delete_records_by_guid(self, entity_type: str, guids: set[str]) -> int:
        """Delete records by GUID set. Cascades to child tables for vouchers.

        Args:
            entity_type: The entity type (e.g. "ledger", "voucher").
            guids: Set of GUIDs to delete.

        Returns:
            Number of records deleted.
        """
        if not guids or self._conn is None:
            return 0
        table_map: dict[str, str] = {
            "ledger": "mst_ledger",
            "group": "mst_group",
            "stock_item": "mst_stock_item",
            "voucher_type": "mst_voucher_type",
            "unit": "mst_unit",
            "stock_group": "mst_stock_group",
            "cost_center": "mst_cost_center",
            "godown": "mst_godown",
            "voucher": "trn_voucher",
        }
        table = table_map.get(entity_type)
        if table is None:
            return 0

        guid_list = list(guids)
        placeholders = ",".join(["?"] * len(guid_list))
        deleted = 0
        try:
            if entity_type == "voucher":
                for guid in guid_list:
                    self._conn.execute(
                        "DELETE FROM trn_bill WHERE voucher_guid = ?", [guid]
                    )
                    self._conn.execute(
                        "DELETE FROM trn_cost_centre WHERE voucher_guid = ?",
                        [guid],
                    )
                    self._conn.execute(
                        "DELETE FROM trn_inventory_entry WHERE voucher_guid = ?",
                        [guid],
                    )
                    self._conn.execute(
                        "DELETE FROM trn_ledger_entry WHERE voucher_guid = ?",
                        [guid],
                    )
            self._conn.execute(
                f"DELETE FROM {table} WHERE guid IN ({placeholders})",
                guid_list,
            )
            deleted = len(guids)
            self._conn.commit()
        except Exception as exc:
            logger.warning(
                "Failed to delete {} records for {}: {}",
                len(guids),
                entity_type,
                exc,
            )
            try:
                self._conn.rollback()
            except Exception:
                pass
        return deleted
