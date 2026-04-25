# SPECS.md — TallyBridge Technical Specifications

> **This is a reference document.** Claude reads the section relevant to the current TASKS.md item.
> Section numbers match TASKS.md references (e.g. "Spec: SPECS.md §4").

---

## §1 — exceptions.py

**File:** `src/tallybridge/exceptions.py`

```python
class TallyConnectionError(Exception):
    """TallyPrime is not running or not reachable on the configured host:port.
    
    Always include a human-readable fix instruction in the message, e.g.:
    "Could not connect to Tally on localhost:9000.
     Is TallyPrime open? Enable: F1 > Settings > Connectivity >
     TallyPrime acts as = Server, Port = 9000"
    """

class TallyDataError(Exception):
    """Tally returned a LINEERROR or structurally invalid XML response.
    
    Store the raw response in self.raw_response for debugging.
    Extract and store the error text in self.error_text.
    """

class TallySyncError(Exception):
    """An unrecoverable sync failure (data corruption, programmer error).
    
    NOT raised for temporary Tally-offline situations — those return
    SyncResult(success=False). Only raise this for situations where
    continuing would corrupt the cache.
    """

class TallyBridgeCacheError(Exception):
    """DuckDB is inaccessible, corrupted, or an unrecoverable SQL error occurred."""
```

**Tests — `tests/test_exceptions.py`:**
1. Each exception can be instantiated with a string message and raised/caught
2. Each is a subclass of `Exception`
3. `TallyDataError` stores `raw_response` and `error_text` as attributes

---

## §2 — config.py

**File:** `src/tallybridge/config.py`

```python
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class TallyBridgeConfig(BaseSettings):
    # Tally connection
    tally_host: str = "localhost"
    tally_port: int = 9000
    tally_company: str | None = None      # None = use active company

    # Local cache
    db_path: str = "tallybridge.duckdb"

    # Sync behaviour
    sync_frequency_minutes: int = 5

    # Logging
    log_level: str = "INFO"               # DEBUG | INFO | WARNING | ERROR

    # Cloud (optional paid tier)
    supabase_url: str | None = None
    supabase_key: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="TALLYBRIDGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR"}
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.upper()

    @field_validator("tally_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("tally_port must be between 1 and 65535")
        return v

    async def validate_tally_connection(self) -> None:
        """Ping Tally and raise TallyConnectionError if unreachable."""

    @property
    def tally_url(self) -> str:
        return f"http://{self.tally_host}:{self.tally_port}"


_config_instance: TallyBridgeConfig | None = None

def get_config() -> TallyBridgeConfig:
    """Return cached singleton. Safe to call from anywhere."""
    global _config_instance
    if _config_instance is None:
        _config_instance = TallyBridgeConfig()
    return _config_instance
```

**Tests — `tests/test_config.py`:**
1. Default field values match the spec
2. `TALLYBRIDGE_TALLY_PORT=9001` env var overrides the default
3. `TALLYBRIDGE_LOG_LEVEL=debug` is normalised to `"DEBUG"`
4. Invalid `log_level` raises `ValidationError`
5. `get_config()` returns the same instance on repeated calls
6. `validate_tally_connection()` raises `TallyConnectionError` when nothing is listening (test with a port that has no server)

---

## §3 — models/

### §3a — models/master.py

**File:** `src/tallybridge/models/master.py`

```python
from decimal import Decimal
from pydantic import BaseModel

class TallyLedger(BaseModel):
    name: str
    guid: str
    alter_id: int
    parent_group: str
    opening_balance: Decimal = Decimal("0")
    closing_balance: Decimal = Decimal("0")
    is_revenue: bool = False
    affects_gross_profit: bool = False
    gstin: str | None = None
    party_name: str | None = None
    bill_credit_period: int | None = None   # days

class TallyGroup(BaseModel):
    name: str
    guid: str
    alter_id: int
    parent: str
    primary_group: str
    is_revenue: bool = False
    affects_gross_profit: bool = False
    net_debit_credit: str = "Dr"            # "Dr" or "Cr"

class TallyStockItem(BaseModel):
    name: str
    guid: str
    alter_id: int
    parent_group: str
    unit: str
    gst_rate: Decimal | None = None
    hsn_code: str | None = None
    opening_quantity: Decimal = Decimal("0")
    opening_rate: Decimal = Decimal("0")
    closing_quantity: Decimal = Decimal("0")
    closing_value: Decimal = Decimal("0")

class TallyGodown(BaseModel):
    name: str
    guid: str
    alter_id: int
    parent: str | None = None

class TallyVoucherType(BaseModel):
    name: str
    guid: str
    alter_id: int
    parent: str                             # Sales, Purchase, Payment, Receipt, etc.
    number_series: str | None = None

class TallyUnit(BaseModel):
    """Unit of measure — Nos, Kgs, Ltrs, Boxes, etc."""
    name: str
    guid: str
    alter_id: int
    unit_type: str = "Simple"               # Simple | Compound
    base_units: str | None = None           # For compound units e.g. "Dozen of Nos"
    decimal_places: int = 0                 # Precision for quantities
    symbol: str | None = None              # Display symbol e.g. "Kg"

class TallyStockGroup(BaseModel):
    """Parent grouping for stock items — mirrors TallyGroup for ledgers."""
    name: str
    guid: str
    alter_id: int
    parent: str                             # Parent stock group name
    should_quantities_add: bool = True      # Whether quantities roll up to parent

class TallyCostCenter(BaseModel):
    """Cost centre for department/project-wise tracking.
    
    Most Indian businesses use cost centres to split P&L by department,
    project, or branch. Required for cost-centre-wise reports.
    """
    name: str
    guid: str
    alter_id: int
    parent: str                             # Parent cost centre name
    email: str | None = None
    cost_centre_type: str = "Primary"       # Primary | Sub
```

### §3b — models/voucher.py

**File:** `src/tallybridge/models/voucher.py`

```python
from decimal import Decimal
from datetime import date
from pydantic import BaseModel

class TallyVoucherEntry(BaseModel):
    ledger_name: str
    amount: Decimal                         # Positive = Dr, Negative = Cr

class TallyInventoryEntry(BaseModel):
    stock_item_name: str
    quantity: Decimal = Decimal("0")
    rate: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    godown: str | None = None
    batch: str | None = None

class TallyVoucher(BaseModel):
    guid: str
    alter_id: int
    voucher_number: str
    voucher_type: str
    date: date
    effective_date: date | None = None      # GST effective date — can differ from date
    reference: str | None = None
    narration: str | None = None
    is_cancelled: bool = False
    is_optional: bool = False
    is_postdated: bool = False              # Post-dated cheques/entries
    is_void: bool = False                   # Void ≠ cancelled in Tally
    party_ledger: str | None = None
    party_gstin: str | None = None
    place_of_supply: str | None = None
    due_date: date | None = None            # BASICDUEDATEOFPYMT — on purchase invoices
    entered_by: str | None = None           # Tally user who entered — audit trail
    ledger_entries: list[TallyVoucherEntry] = []
    inventory_entries: list[TallyInventoryEntry] = []
    total_amount: Decimal = Decimal("0")   # Sum of Dr-side entries
    gst_amount: Decimal = Decimal("0")     # Sum of GST ledger entries
```

### §3c — models/report.py

**File:** `src/tallybridge/models/report.py`

```python
from decimal import Decimal
from datetime import date
from pydantic import BaseModel

class TrialBalanceLine(BaseModel):
    ledger: str
    group: str
    opening_debit: Decimal = Decimal("0")
    opening_credit: Decimal = Decimal("0")
    period_debit: Decimal = Decimal("0")
    period_credit: Decimal = Decimal("0")
    closing_debit: Decimal = Decimal("0")
    closing_credit: Decimal = Decimal("0")

class OutstandingBill(BaseModel):
    party_name: str
    bill_date: date
    bill_number: str
    bill_amount: Decimal
    paid_amount: Decimal = Decimal("0")
    outstanding_amount: Decimal
    overdue_days: int = 0
    voucher_type: str                       # "Sales" or "Purchase"

class DailyDigest(BaseModel):
    company: str
    digest_date: date
    total_sales: Decimal = Decimal("0")
    total_purchases: Decimal = Decimal("0")
    cash_balance: Decimal = Decimal("0")
    bank_balance: Decimal = Decimal("0")
    top_overdue_receivables: list[OutstandingBill] = []
    gst_filings_due: list[str] = []
    low_stock_items: list[str] = []

class StockAgingLine(BaseModel):
    """One row in a stock aging report."""
    item_name: str
    unit: str
    closing_quantity: Decimal
    closing_value: Decimal
    last_movement_date: date | None = None  # Date of last purchase or sale
    days_since_movement: int = 0
    aging_bucket: str = ""                  # e.g. "0-30", "31-60", "61-90", "90+"

class SyncResult(BaseModel):
    entity_type: str
    records_synced: int = 0
    alter_id_before: int = 0
    alter_id_after: int = 0
    duration_seconds: float = 0.0
    success: bool = True
    error_message: str | None = None
```

**Tests — `tests/test_models.py`:**
1. Every model instantiates correctly with valid data
2. Pydantic rejects wrong types (e.g. string for `alter_id`)
3. Optional fields default to `None`
4. `Decimal` fields accept string, int, and Decimal inputs
5. `TallyVoucher.ledger_entries` defaults to empty list (not shared mutable default)
6. `is_cancelled=True` round-trips through model serialisation correctly
7. `TallyVoucher.effective_date` can differ from `TallyVoucher.date`
8. `TallyVoucher.is_postdated=True` and `is_void=True` are independent booleans
9. `TallyUnit` with `unit_type="Compound"` and `base_units` set instantiates correctly
10. `TallyCostCenter` with all optional fields as `None` instantiates correctly
11. `StockAgingLine.aging_bucket` accepts arbitrary strings (bucket label is display-only)

---

## §4 — connection.py

**File:** `src/tallybridge/connection.py`

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from loguru import logger

class TallyConnection:
    def __init__(self, config: TallyBridgeConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(timeout=30.0)

    async def ping(self) -> bool:
        """Returns True if Tally responds, False otherwise. Never raises."""

    async def get_company_list(self) -> list[str]:
        """List all company names currently open in Tally.
        
        Raises:
            TallyConnectionError: If Tally is not running.
        """

    async def export_collection(
        self,
        collection_name: str,
        tally_type: str,
        fields: list[str],
        filter_expr: str | None = None,
        company: str | None = None,
    ) -> str:
        """Export a Tally collection and return raw XML string.
        
        Args:
            collection_name: Arbitrary name for this collection (used in XML).
            tally_type: Tally object type: Ledger, Voucher, StockItem, Group, etc.
            fields: List of Tally field names to fetch, e.g. ["NAME", "GUID", "ALTERID"].
            filter_expr: TDL filter expression, e.g. "$ALTERID > 1000". None = no filter.
            company: Company name, or None for the active company.
            
        Raises:
            TallyConnectionError: Tally not running.
            TallyDataError: Tally returned LINEERROR.
        """

    async def get_alter_id_max(
        self, tally_type: str, company: str | None = None
    ) -> int:
        """Return current maximum AlterID for a Tally type. Returns 0 if none."""

    async def post_xml(self, xml_body: str) -> str:
        """POST UTF-8 XML to Tally, return UTF-16 decoded response string.
        Internal use only — call the typed methods above instead.
        
        Raises:
            TallyConnectionError: On connection refused.
        """

    async def close(self) -> None:
        await self._client.aclose()
```

**Implementation requirements:**
- `post_xml` sends `Content-Type: text/xml; charset=utf-8`
- Decode response: `response.content.decode('utf-16', errors='replace')`
- `httpx.ConnectError` and `httpx.ConnectTimeout` → raise `TallyConnectionError` with setup instructions
- `<LINEERROR>` in response text → raise `TallyDataError` with extracted error text
- Apply tenacity retry decorator to `post_xml`: 3 attempts, 2-second wait, only on `TallyConnectionError`
- Build XML request using string templates (not xml.etree — the structure is fixed)
- All logging: `logger.debug(...)` for request/response, `logger.warning(...)` for retries

**Tests — `tests/test_connection.py`** (use `pytest-httpserver`):
1. `ping()` returns `True` when server responds with any 200
2. `ping()` returns `False` when port has nothing listening
3. `export_collection()` returns XML string when server returns valid XML
4. `export_collection()` raises `TallyConnectionError` when connection refused
5. `export_collection()` raises `TallyDataError` when response contains `<LINEERROR>`
6. `get_alter_id_max()` correctly parses integer from response
7. `post_xml()` sends `Content-Type: text/xml` header (verify via httpserver request inspection)

---

## §5 — parser.py

**File:** `src/tallybridge/parser.py`

```python
import xml.etree.ElementTree as ET   # stdlib only — no lxml, no BeautifulSoup
from decimal import Decimal, InvalidOperation
from datetime import date
from loguru import logger

class TallyXMLParser:

    @staticmethod
    def parse_amount(amount_str: str | None) -> Decimal:
        """Parse Tally amount string to signed Decimal.
        
        "1234.56 Dr"  → Decimal("1234.56")
        "1234.56 Cr"  → Decimal("-1234.56")
        "-500.00"     → Decimal("-500.00")    # already signed
        "" or None    → Decimal("0")
        
        On any parse failure: log warning, return Decimal("0").
        """

    @staticmethod
    def parse_date(date_str: str | None) -> date | None:
        """Parse Tally YYYYMMDD to Python date. Returns None on failure."""

    @staticmethod
    def parse_bool(bool_str: str | None) -> bool:
        """'Yes' → True, anything else → False."""

    @staticmethod
    def get_text(element: ET.Element | None, tag: str, default: str = "") -> str:
        """Safely get text from a child tag. Returns default if missing or empty."""

    def parse_ledgers(self, xml: str) -> list[TallyLedger]: ...
    def parse_groups(self, xml: str) -> list[TallyGroup]: ...
    def parse_stock_items(self, xml: str) -> list[TallyStockItem]: ...
    def parse_voucher_types(self, xml: str) -> list[TallyVoucherType]: ...

    def parse_vouchers(self, xml: str) -> list[TallyVoucher]:
        """Parse voucher collection XML.
        
        Each <VOUCHER> element contains:
        - Direct fields: GUID, ALTERID, DATE, VOUCHERNUMBER, VOUCHERTYPENAME, etc.
        - <LEDGERENTRIES.LIST> sub-elements with LEDGERNAME and AMOUNT
        - <INVENTORYENTRIES.LIST> sub-elements with STOCKITEMNAME, ACTUALQTY, RATE, AMOUNT
        """

    def parse_outstanding_bills(self, xml: str) -> list[OutstandingBill]: ...
```

**Implementation requirements:**
- All `parse_*` methods: catch all exceptions, log a warning, return `[]` on catastrophic failure — never propagate exceptions to callers
- For individual record failures: log a warning with the record's raw XML fragment, skip that record, continue parsing the rest
- Unicode is automatic with ElementTree — no special handling needed, but test it

**Tests — `tests/test_parser.py`:**
1. `parse_amount("1234.56 Dr")` → `Decimal("1234.56")`
2. `parse_amount("1234.56 Cr")` → `Decimal("-1234.56")`
3. `parse_amount("-500.00")` → `Decimal("-500.00")`
4. `parse_amount("")` and `parse_amount(None)` → `Decimal("0")`
5. `parse_date("20250415")` → `date(2025, 4, 15)`
6. `parse_date("")` → `None`
7. `parse_bool("Yes")` → `True`; `parse_bool("No")` → `False`; `parse_bool(None)` → `False`
8. `parse_ledgers(xml)` with 3-ledger XML returns 3 `TallyLedger` instances with correct field values
9. `parse_ledgers(xml)` with Unicode ledger name `"शर्मा ट्रेडर्स"` parses without error
10. `parse_vouchers(xml)` returns correct nested `ledger_entries` list
11. `parse_vouchers(xml)` sets `is_cancelled=True` for a cancelled voucher
12. All `parse_*` methods return `[]` on completely malformed XML (no exception raised)

---

## §6 — cache.py

**File:** `src/tallybridge/cache.py`

### Schema SQL (define as `SCHEMA_SQL` constant)

```sql
-- Master tables
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

-- Transaction tables
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
    voucher_guid TEXT NOT NULL REFERENCES trn_voucher(guid) ON DELETE CASCADE,
    ledger_name  TEXT NOT NULL,
    amount       DECIMAL(18,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS trn_inventory_entry (
    id               BIGINT DEFAULT nextval('seq_entry_id') PRIMARY KEY,
    voucher_guid     TEXT NOT NULL REFERENCES trn_voucher(guid) ON DELETE CASCADE,
    stock_item_name  TEXT NOT NULL,
    quantity         DECIMAL(18,4) DEFAULT 0,
    rate             DECIMAL(18,4) DEFAULT 0,
    amount           DECIMAL(18,4) DEFAULT 0,
    godown           TEXT,
    batch            TEXT
);

-- Sync and migration tracking
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
```

### Class definition

```python
import duckdb
from loguru import logger

# Migration entries: (version: int, description: str, sql: str)
MIGRATIONS: list[tuple[int, str, str]] = [
    # (1, "initial schema", SCHEMA_SQL),  ← add future migrations here
]

class TallyCache:
    def __init__(self, db_path: str) -> None:
        """Open or create DuckDB. Calls initialize() automatically."""

    def initialize(self) -> None:
        """Create schema if not exists. Apply any pending migrations. Idempotent."""

    # ── Upsert operations ──────────────────────────────────────────────

    def upsert_ledgers(self, ledgers: list[TallyLedger]) -> int:
        """INSERT OR REPLACE ledgers by guid. Returns affected row count."""

    def upsert_groups(self, groups: list[TallyGroup]) -> int: ...
    def upsert_stock_items(self, items: list[TallyStockItem]) -> int: ...
    def upsert_voucher_types(self, vtypes: list[TallyVoucherType]) -> int: ...
    def upsert_units(self, units: list[TallyUnit]) -> int: ...
    def upsert_stock_groups(self, groups: list[TallyStockGroup]) -> int: ...
    def upsert_cost_centers(self, centers: list[TallyCostCenter]) -> int: ...

    def upsert_vouchers(self, vouchers: list[TallyVoucher]) -> int:
        """Upsert vouchers and replace their child entries atomically.
        
        For each voucher:
        1. INSERT OR REPLACE the trn_voucher row (CASCADE deletes old entries)
        2. INSERT all ledger_entries
        3. INSERT all inventory_entries
        Uses a transaction — all vouchers in the batch commit together or not at all.
        """

    # ── Sync state ────────────────────────────────────────────────────

    def get_last_alter_id(self, entity_type: str) -> int:
        """Return last synced AlterID for entity_type, or 0 if not yet synced."""

    def update_sync_state(
        self, entity_type: str, last_alter_id: int, record_count: int
    ) -> None:
        """Upsert a sync_state row after successful sync."""

    def get_sync_status(self) -> dict[str, dict]:
        """Return {entity_type: {last_alter_id, last_sync_at, record_count}} for all rows."""

    # ── Query helpers ─────────────────────────────────────────────────

    def query(self, sql: str, params: list | None = None) -> list[dict]:
        """Execute parameterised SELECT, return list of row dicts. Read-only."""

    def get_ledger(self, name: str) -> TallyLedger | None: ...
    def get_ledger_balance(self, name: str) -> Decimal: ...
    def get_outstanding_receivables(self) -> list[OutstandingBill]: ...
    def get_outstanding_payables(self) -> list[OutstandingBill]: ...
    def get_trial_balance(self, from_date: date, to_date: date) -> list[TrialBalanceLine]: ...

    # ── Health ────────────────────────────────────────────────────────

    def health_check(self) -> dict:
        """Return {record_counts, last_sync_times, db_size_mb, schema_version}."""

    def close(self) -> None:
        """Close DuckDB connection."""
```

**Tests — `tests/test_cache.py`** (use `tmp_path` fixture for all DB paths):
1. DB file is created if it doesn't exist
2. `initialize()` is idempotent — safe to call twice without error
3. `upsert_ledgers([ledger])` inserts new record, `query("SELECT COUNT(*) ...")` returns 1
4. `upsert_ledgers([same_guid_new_alter_id])` updates in place — count stays 1, alter_id updated
5. `upsert_vouchers([voucher])` inserts voucher + ledger entries
6. `upsert_vouchers([same_voucher_different_entries])` replaces entries — old entries gone
7. `get_last_alter_id("ledger")` returns 0 before any sync
8. After `update_sync_state("ledger", 500, 100)`, a fresh `TallyCache(same_path)` returns `get_last_alter_id("ledger") == 500`
9. `health_check()` returns dict with keys: `record_counts`, `last_sync_times`, `db_size_mb`

---

## §7 — sync.py

**File:** `src/tallybridge/sync.py`

```python
import asyncio
from typing import Literal
from loguru import logger

# Entity config: maps entity_type string to (tally_type, fields, parse_method, upsert_method)
ENTITY_CONFIG: dict[str, dict] = {
    "group": {
        "tally_type": "Group",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT", "PRIMARYGROUP",
                   "ISREVENUE", "AFFECTSGROSSPROFIT", "NETDEBITCREDIT"],
    },
    "ledger": {
        "tally_type": "Ledger",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT", "OPENINGBALANCE",
                   "CLOSINGBALANCE", "ISREVENUE", "AFFECTSGROSSPROFIT",
                   "GSTIN", "LEDMAILINGNAME"],
    },
    "voucher_type": {
        "tally_type": "VoucherType",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT"],
    },
    "unit": {
        "tally_type": "Unit",
        "fields": ["NAME", "GUID", "ALTERID", "UNITTYPE", "BASEUNITS",
                   "DECIMALPLACES", "SYMBOL"],
    },
    "stock_group": {
        "tally_type": "StockGroup",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT", "SHOULDQUANTITIESADD"],
    },
    "stock_item": {
        "tally_type": "StockItem",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT", "BASEUNITS",
                   "GSTRATE", "HSNCODE", "OPENINGBALANCE", "CLOSINGBALANCE"],
    },
    "cost_center": {
        "tally_type": "CostCentre",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT", "EMAIL",
                   "COSTCENTRETYPE"],
    },
    "voucher": {
        "tally_type": "Voucher",
        "fields": ["GUID", "ALTERID", "DATE", "EFFECTIVEDATE", "VOUCHERNUMBER",
                   "VOUCHERTYPENAME", "REFERENCE", "NARRATION",
                   "PARTYLEDGERNAME", "PARTYMAILINGNAME", "PLACEOFSUPPLY",
                   "BASICDUEDATEOFPYMT", "ENTEREDBY",
                   "ISCANCELLED", "ISOPTIONAL", "ISPOSTDATED", "ISVOID",
                   "LEDGERENTRIES", "INVENTORYENTRIES"],
    },
}

# Sync order matters — each type may reference types above it in the list
# group/unit/stock_group before stock_item; group before ledger; all masters before voucher
SYNC_ORDER: list[str] = [
    "group", "ledger", "voucher_type",
    "unit", "stock_group", "stock_item",
    "cost_center", "voucher",
]
VOUCHER_BATCH_SIZE = 1000

class TallySyncEngine:
    def __init__(
        self,
        connection: TallyConnection,
        cache: TallyCache,
        parser: TallyXMLParser,
    ) -> None:
        self._connection = connection
        self._cache = cache
        self._parser = parser
        self._lock = asyncio.Lock()

    async def sync_entity(
        self,
        entity_type: Literal[
            "ledger", "group", "stock_item", "voucher_type", "voucher",
            "unit", "stock_group", "cost_center",
        ],
    ) -> SyncResult:
        """Sync one entity. Returns SyncResult — NEVER raises.
        
        On any exception: log it, return SyncResult(success=False, error_message=str(e)).
        """

    async def sync_all(self) -> dict[str, SyncResult]:
        """Sync all entities in SYNC_ORDER. Holds _lock for the full cycle."""

    async def full_sync(self) -> dict[str, SyncResult]:
        """Reset all AlterIDs to 0 in sync_state, then run sync_all()."""

    async def run_continuous(self, frequency_minutes: int = 5) -> None:
        """Run sync_all() every frequency_minutes using asyncio.sleep().
        
        When Tally unavailable: log warning, sleep, retry. Never crash.
        """

    async def is_tally_available(self) -> bool:
        """Non-blocking Tally ping."""
```

**Tests — `tests/test_sync.py`** (use `AsyncMock` — no real DB or HTTP):
1. `sync_entity("ledger")` returns `SyncResult(records_synced=5, success=True)` when mock connection returns 5 records with higher AlterID
2. `sync_entity("ledger")` returns `SyncResult(records_synced=0, success=True)` when AlterID unchanged
3. `sync_entity("ledger")` returns `SyncResult(success=False)` — not raises — when connection raises `TallyConnectionError`
4. `sync_all()` calls `sync_entity` in the exact order defined in `SYNC_ORDER`
5. `full_sync()` calls `update_sync_state("...", 0, 0)` for every entity before syncing
6. A second concurrent `sync_all()` call waits for the first to finish (asyncio.Lock test)

---

## §8 — query.py

**File:** `src/tallybridge/query.py`

```python
from typing import Literal
from decimal import Decimal
from datetime import date, datetime

class TallyQuery:
    def __init__(self, cache: TallyCache) -> None:
        self._cache = cache

    # ── Company Overview ────────────────────────────────────────────────

    def get_daily_digest(self, as_of_date: date | None = None) -> DailyDigest:
        """Complete business summary for the given date (default: today).
        
        Includes total sales, total purchases, cash balance, bank balance,
        top 5 overdue receivables, and low-stock alerts.
        """

    # ── Balances ────────────────────────────────────────────────────────

    def get_ledger_balance(self, ledger_name: str, as_of_date: date | None = None) -> Decimal:
        """Closing balance as of date. Positive = Dr, Negative = Cr.
        Raises KeyError if ledger not found in cache.
        """

    def get_cash_balance(self, as_of_date: date | None = None) -> Decimal:
        """Sum of all ledgers under the 'Cash-in-Hand' group."""

    def get_bank_balance(self, as_of_date: date | None = None) -> Decimal:
        """Sum of all ledgers under the 'Bank Accounts' group."""

    def get_trial_balance(self, from_date: date, to_date: date) -> list[TrialBalanceLine]:
        """Trial balance for the period."""

    # ── Outstanding ─────────────────────────────────────────────────────

    def get_receivables(
        self,
        as_of_date: date | None = None,
        overdue_only: bool = False,
        min_days_overdue: int = 0,
    ) -> list[OutstandingBill]:
        """Outstanding sales invoices. overdue_only=True filters to past-due only."""

    def get_payables(
        self,
        as_of_date: date | None = None,
        overdue_only: bool = False,
    ) -> list[OutstandingBill]:
        """Outstanding purchase invoices."""

    def get_party_outstanding(self, party_name: str) -> dict:
        """Full position for one party.
        
        Returns:
            {
                "total_receivable": Decimal,
                "total_payable": Decimal,
                "net_position": Decimal,    # positive = they owe us
                "bills": list[OutstandingBill],
            }
        """

    # ── Sales and Purchases ─────────────────────────────────────────────

    def get_sales_summary(
        self,
        from_date: date,
        to_date: date,
        group_by: Literal["day", "week", "month", "party", "item"] = "day",
    ) -> list[dict]:
        """Sales summary grouped by dimension.
        
        Returns per group_by:
            day/week/month: {period, total_amount, voucher_count}
            party:          {party_name, total_amount, voucher_count}
            item:           {item_name, total_quantity, total_amount}
        """

    def get_purchases_summary(
        self, from_date: date, to_date: date, group_by: str = "day"
    ) -> list[dict]: ...

    def get_vouchers(
        self,
        voucher_type: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        party_name: str | None = None,
        limit: int = 100,
    ) -> list[TallyVoucher]:
        """Vouchers matching filters. Excludes cancelled and optional by default."""

    # ── Inventory ───────────────────────────────────────────────────────

    def get_stock_summary(self) -> list[dict]:
        """All items: [{name, unit, closing_quantity, closing_value}]"""

    def get_low_stock_items(
        self, threshold_quantity: Decimal = Decimal("0")
    ) -> list[TallyStockItem]:
        """Items with closing_quantity <= threshold_quantity."""

    def get_stock_aging(
        self,
        as_of_date: date | None = None,
        bucket_days: list[int] | None = None,
    ) -> list[StockAgingLine]:
        """Stock aging analysis — how long has stock been sitting?
        
        Args:
            as_of_date: Analyse as of this date (default: today).
            bucket_days: Aging bucket boundaries in days.
                         Default: [30, 60, 90, 180] → buckets
                         "0-30", "31-60", "61-90", "91-180", "180+"
        
        Returns list of StockAgingLine, one per stock item that has
        closing_quantity > 0. Items with no movement history show
        days_since_movement = 0 and bucket = "No Movement".
        
        Implementation note: calculate last_movement_date as the MAX(date)
        of any voucher in trn_inventory_entry for that stock item.
        """

    # ── GST ─────────────────────────────────────────────────────────────

    def get_gst_summary(self, from_date: date, to_date: date) -> dict:
        """GST summary for the period.
        
        Returns: {
            total_cgst_collected, total_sgst_collected, total_igst_collected,
            total_cgst_paid, total_sgst_paid, total_igst_paid,
            net_itc, net_liability
        }
        All values are Decimal.
        """

    # ── Cost Centres ─────────────────────────────────────────────────────

    def get_cost_center_summary(
        self,
        from_date: date,
        to_date: date,
        cost_center_name: str | None = None,
    ) -> list[dict]:
        """Income and expense breakdown by cost centre for the period.
        
        Args:
            from_date: Period start.
            to_date: Period end.
            cost_center_name: Filter to a single cost centre, or None for all.
        
        Returns: [{
            "cost_center": str,
            "total_income": Decimal,
            "total_expense": Decimal,
            "net": Decimal,           # income - expense
        }]
        
        Implementation note: cost centre allocations are in
        trn_ledger_entry.cost_center (add this column in a future
        migration when cost centre entry support is added to the parser).
        For v0.1, return data from mst_cost_center joined to vouchers
        where the party_ledger matches — this is an approximation.
        Add a # NOTE: comment in the implementation explaining the limitation.
        """

    # ── Search ──────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 20) -> dict:
        """Case-insensitive search across ledger names, party names, narrations.
        
        Returns: {
            "ledgers": list[TallyLedger],
            "vouchers": list[TallyVoucher],
            "parties": list[str],
        }
        Uses SQL ILIKE. Empty query returns empty results.
        """
```

**Tests — `tests/test_query.py`** (use `tally_query` fixture from conftest):
- At minimum 3 test cases per method: normal result, empty result, edge case
- `get_daily_digest().total_sales` must equal sum of sales voucher amounts in test data
- `get_receivables(overdue_only=True)` returns only bills with `overdue_days > 0`
- `get_sales_summary(group_by="party")` groups correctly — one row per party
- `get_sales_summary(group_by="day")` returns one row per date
- `search("sharma")` finds ledgers and vouchers containing "sharma" (case-insensitive)
- `get_vouchers()` excludes `is_cancelled=True` and `is_void=True` vouchers by default
- `get_ledger_balance("nonexistent")` raises `KeyError`
- `get_stock_aging()` returns `StockAgingLine` instances with correct `aging_bucket` values
- `get_stock_aging(bucket_days=[60, 120])` uses the custom bucket boundaries
- `get_cost_center_summary(from_date, to_date)` returns list of dicts with expected keys

---

## §9 — mcp/tools.py + mcp/server.py

### §9a — mcp/tools.py

**File:** `src/tallybridge/mcp/tools.py`

Define `TOOLS: list[dict]` with these 12 entries:

| # | name | description (must be useful to an AI agent) | required inputs |
|---|------|----------------------------------------------|-----------------|
| 1 | `get_tally_digest` | Complete business summary: sales, purchases, balances, overdue parties | optional `date` (YYYY-MM-DD) |
| 2 | `get_ledger_balance` | Closing balance of any ledger. Positive=Dr, Negative=Cr | `ledger_name`, optional `date` |
| 3 | `get_receivables` | Outstanding sales invoices — money owed to the business | optional `overdue_only` bool, `min_days_overdue` int |
| 4 | `get_party_outstanding` | Full receivable/payable position with one party | `party_name` |
| 5 | `get_sales_summary` | Sales by day/week/month/party/item for a date range | `from_date`, `to_date`, optional `group_by` enum |
| 6 | `get_gst_summary` | GST collected, ITC, and net liability for a period | `from_date`, `to_date` |
| 7 | `search_tally` | Search ledgers, parties, voucher narrations | `query` string, optional `limit` |
| 8 | `get_sync_status` | When data was last synced and record counts | none |
| 9 | `get_low_stock` | Stock items at or below quantity threshold | optional `threshold` number |
| 10 | `get_stock_aging` | How long stock has been sitting — aging by 0-30, 31-60, 61-90, 90+ day buckets | optional `date`, optional `bucket_days` array |
| 11 | `get_cost_center_summary` | Income and expense breakdown by department or project cost centre | `from_date`, `to_date`, optional `cost_center_name` |
| 12 | `query_tally_data` | Run a custom SQL SELECT on the local cache. Tables: mst_ledger, mst_group, mst_stock_item, mst_unit, mst_stock_group, mst_cost_center, trn_voucher, trn_ledger_entry, trn_inventory_entry | `sql` string, optional `limit` (max 1000) |

Each entry must have `name`, `description`, and `input_schema` (valid JSON Schema object).

### §9b — mcp/server.py

**File:** `src/tallybridge/mcp/server.py`

```python
# Entry point: python -m tallybridge.mcp.server (stdio transport)

FORBIDDEN_SQL = frozenset([
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
    "CREATE", "TRUNCATE", "EXEC", "EXECUTE",
])

def is_safe_sql(sql: str) -> bool:
    tokens = sql.upper().split()
    return not any(t in FORBIDDEN_SQL for t in tokens)

# Server startup:
# 1. Load TallyBridgeConfig from environment
# 2. Initialize TallyCache(config.db_path)
# 3. Initialize TallyQuery(cache)
# 4. Register all tools from TOOLS list
# 5. Dispatch tool calls to TallyQuery methods
# 6. Return JSON-serialisable dicts (convert Decimal → str, date → isoformat)

# Error contract: EVERY tool handler must catch all exceptions and return:
# {"error": True, "message": str(e), "tool": tool_name}
# The server process must never crash due to a tool error.
```

**Tests — `tests/test_mcp.py`:**
1. The server registers exactly 12 tools
2. `get_tally_digest` returns a dict with keys: `company`, `digest_date`, `total_sales`
3. `query_tally_data` with `"DROP TABLE mst_ledger"` returns `{"error": True, "message": "Only SELECT queries are allowed..."}`
4. `query_tally_data` with `"SELECT * FROM mst_ledger LIMIT 1"` returns a list
5. Any tool returns `{"error": True, ...}` — not raises — when the cache raises an exception

---

## §10 — cli.py

**File:** `src/tallybridge/cli.py`  
**Framework:** `typer` + `rich`

### Commands

```
tallybridge init                        # interactive setup wizard (5 steps)
tallybridge config show                 # print config, mask supabase_key
tallybridge config set KEY VALUE        # write KEY=VALUE to .env
tallybridge status                      # Rich table: sync status per entity
tallybridge sync                        # one-time sync now
tallybridge sync --full                 # force full re-sync
tallybridge sync --watch                # continuous sync, Ctrl-C to stop
tallybridge service install             # Windows: install as auto-start service
tallybridge service start               # Windows: start the service
tallybridge service stop                # Windows: stop the service
tallybridge service uninstall           # Windows: remove the service
tallybridge mcp                         # start MCP server (stdio)
tallybridge mcp --http --port INT       # start MCP server (HTTP)
tallybridge doctor                      # diagnostic checks
tallybridge logs                        # tail recent loguru log file
```

### `init` wizard (5 steps)

```
Welcome to TallyBridge! Let's connect to your TallyPrime.

[1/5] Is TallyPrime running on this computer? [Y/n]:
[2/5] Where is TallyPrime?
      1. This computer (localhost:9000)
      2. Another computer on the network
[3/5] Connecting... [spinner] → List companies → user picks one
[4/5] Where to store data? [default path]:
[5/5] How often to sync? [5] minutes

→ Runs first sync with progress bars
→ Prints "TallyBridge is ready!" with next steps
```

### `doctor` checks (7 items, printed as ✓ / ✗)

1. Python version ≥ 3.11
2. Tally reachable on configured host:port
3. DuckDB file exists and readable
4. Last sync was < 30 minutes ago
5. DuckDB has > 0 ledger records (data has been synced)
6. MCP server importable without error
7. (Windows only) Windows service installed

### Non-Windows behaviour for service commands
Print: `"Windows service management is only available on Windows."` and exit 0.

**Tests — `tests/test_cli.py`** (use `typer.testing.CliRunner`):
1. `tallybridge --help` exits 0 and lists all commands
2. `tallybridge status` prints a table when DB is populated
3. `tallybridge doctor` prints at least 6 check lines with ✓ or ✗
4. `tallybridge sync --full` calls `full_sync()` on the engine (mock the engine)

---

## §11 — tests/conftest.py + tests/mock_tally.py

### §11a — tests/mock_tally.py

**File:** `tests/mock_tally.py`

A module of helpers used by `conftest.py` to set up a `pytest-httpserver` instance.

**Sample data constants** (define at module level):

```python
SAMPLE_LEDGERS = [
    # guid, alter_id, name, parent_group, closing_balance, is_revenue, gstin
    ("guid-cash-001",    100, "Cash",                "Cash-in-Hand",      "45000.00 Dr",  False, None),
    ("guid-hdfc-001",    101, "HDFC Bank",           "Bank Accounts",     "250000.00 Dr", False, None),
    ("guid-icici-001",   102, "ICICI Bank",          "Bank Accounts",     "75000.00 Dr",  False, None),
    ("guid-sales-001",   103, "Sales",               "Sales Accounts",    "850000.00 Cr", True,  None),
    ("guid-purch-001",   104, "Purchase",            "Purchase Accounts", "420000.00 Dr", True,  None),
    ("guid-party-001",   105, "Sharma Trading Co",   "Sundry Debtors",    "75000.00 Dr",  False, "27AABCS1429B1Z1"),
    ("guid-party-002",   106, "Mehta Suppliers",     "Sundry Creditors",  "42000.00 Cr",  False, "27AAACM2850K1Z1"),
    ("guid-party-003",   107, "Patel Enterprises",   "Sundry Debtors",    "35000.00 Dr",  False, None),
    ("guid-cgst-001",    108, "CGST",                "Duties & Taxes",    "12500.00 Cr",  False, None),
    ("guid-hindi-001",   109, "शर्मा एंड कंपनी",    "Sundry Debtors",    "15000.00 Dr",  False, None),
]

SAMPLE_GROUPS = [
    ("guid-grp-001", 10, "Sundry Debtors",    "Current Assets",      "Assets",      False, "Dr"),
    ("guid-grp-002", 11, "Sundry Creditors",  "Current Liabilities", "Liabilities", False, "Cr"),
    ("guid-grp-003", 12, "Sales Accounts",    "Revenue",             "Income",      True,  "Cr"),
]

SAMPLE_UNITS = [
    # guid, alter_id, name, unit_type, symbol, decimal_places
    ("guid-unit-001", 300, "Nos",   "Simple", "Nos", 0),
    ("guid-unit-002", 301, "Kgs",   "Simple", "Kg",  3),
    ("guid-unit-003", 302, "Ltrs",  "Simple", "L",   3),
    ("guid-unit-004", 303, "Boxes", "Simple", "Box", 0),
]

SAMPLE_STOCK_GROUPS = [
    # guid, alter_id, name, parent, should_quantities_add
    ("guid-sg-001", 310, "Stock-in-Trade",  "Primary", True),
    ("guid-sg-002", 311, "Finished Goods",  "Primary", True),
]

SAMPLE_STOCK_ITEMS = [
    # guid, alter_id, name, parent_group, unit, gst_rate, hsn_code,
    # closing_quantity, closing_value
    ("guid-item-001", 200, "Widget A", "Stock-in-Trade", "Nos", 18.0, "8471", 150, "45000.00"),
    ("guid-item-002", 201, "Widget B", "Stock-in-Trade", "Kgs", 12.0, "3926",  80, "24000.00"),
    # Zero-stock item for low-stock tests
    ("guid-item-003", 202, "Widget C", "Stock-in-Trade", "Nos",  5.0, "8473",   0,     "0.00"),
]

SAMPLE_COST_CENTERS = [
    # guid, alter_id, name, parent, cost_centre_type
    ("guid-cc-001", 400, "Head Office",  "Primary", "Primary"),
    ("guid-cc-002", 401, "Mumbai Branch","Primary", "Sub"),
    ("guid-cc-003", 402, "Delhi Branch", "Primary", "Sub"),
]

SAMPLE_VOUCHERS = [
    # guid, alter_id, vtype, date, effective_date, party, number,
    # amount, is_cancelled, is_void, is_postdated, entered_by
    ("guid-v-001", 500, "Sales",    "20250401", "20250401",
     "Sharma Trading Co",  "SI/001/25",  "50000.00", False, False, False, "Admin"),
    ("guid-v-002", 501, "Sales",    "20250405", "20250405",
     "Patel Enterprises",  "SI/002/25",  "35000.00", False, False, False, "Admin"),
    ("guid-v-003", 502, "Sales",    "20250410", "20250410",
     "Sharma Trading Co",  "SI/003/25",  "25000.00", False, False, False, "Admin"),
    ("guid-v-004", 503, "Purchase", "20250403", "20250401",  # effective_date differs — GST test
     "Mehta Suppliers",    "PI/001/25",  "42000.00", False, False, False, "Manager"),
    ("guid-v-005", 504, "Payment",  "20250408", "20250408",
     "Mehta Suppliers",    "PMT/001/25", "20000.00", False, False, False, "Admin"),
    # Cancelled voucher — must be excluded from totals
    ("guid-v-006", 505, "Sales",    "20250412", "20250412",
     "Patel Enterprises",  "SI/004/25",  "15000.00", True,  False, False, "Admin"),
    # Post-dated voucher
    ("guid-v-007", 506, "Payment",  "20250501", "20250501",
     "Sharma Trading Co",  "PMT/002/25", "10000.00", False, False, True,  "Admin"),
]
```

**Helper functions to build XML responses:**

```python
def build_ledger_xml(ledgers: list) -> str:
    """Return Tally-format XML string for ledger collection."""
    # Returns UTF-16 encoded bytes when served, but build as str here

def build_voucher_xml(vouchers: list) -> str:
    """Return Tally-format XML with nested LEDGERENTRIES.LIST.
    Include effective_date, entered_by, is_postdated, is_void fields.
    """

def build_unit_xml(units: list) -> str:
    """Return Tally-format XML for unit of measure collection."""

def build_stock_group_xml(stock_groups: list) -> str:
    """Return Tally-format XML for stock group collection."""

def build_stock_item_xml(items: list) -> str:
    """Return Tally-format XML for stock item collection.
    Include closing_quantity and closing_value for aging tests.
    """

def build_cost_center_xml(cost_centers: list) -> str:
    """Return Tally-format XML for cost centre collection."""

def setup_mock_routes(httpserver) -> None:
    """Register all route handlers on the httpserver instance.
    
    Parse the incoming XML body to determine the requested TYPE:
    - Group       → build_group_xml(SAMPLE_GROUPS)
    - Ledger      → build_ledger_xml(SAMPLE_LEDGERS)
    - VoucherType → minimal voucher type XML
    - Unit        → build_unit_xml(SAMPLE_UNITS)
    - StockGroup  → build_stock_group_xml(SAMPLE_STOCK_GROUPS)
    - StockItem   → build_stock_item_xml(SAMPLE_STOCK_ITEMS)
    - CostCentre  → build_cost_center_xml(SAMPLE_COST_CENTERS)
    - Voucher     → build_voucher_xml(SAMPLE_VOUCHERS)
    
    Return LINEERROR XML when X-Tally-Simulate-Error: true header present.
    All responses must be encoded as UTF-16 bytes.
    """
```

Tally responses must be returned as `response.content.decode('utf-16')` would produce —
i.e., serve the response bytes encoded as UTF-16.

### §11b — tests/conftest.py

```python
import pytest
from pytest_httpserver import HTTPServer

@pytest.fixture(scope="session")
def mock_tally_server(httpserver: HTTPServer):
    """Running mock Tally HTTP server with all sample data routes."""
    from tests.mock_tally import setup_mock_routes
    setup_mock_routes(httpserver)
    return httpserver

@pytest.fixture
def tmp_db(tmp_path):
    """Fresh TallyCache with schema initialised, empty data."""
    from tallybridge.cache import TallyCache
    cache = TallyCache(str(tmp_path / "test.duckdb"))
    cache.initialize()
    yield cache
    cache.close()

@pytest.fixture
def populated_db(tmp_db):
    """TallyCache pre-loaded with all SAMPLE_* data via upsert methods."""
    from tests.mock_tally import (
        SAMPLE_LEDGERS, SAMPLE_GROUPS, SAMPLE_VOUCHERS,
        SAMPLE_UNITS, SAMPLE_STOCK_GROUPS, SAMPLE_STOCK_ITEMS,
        SAMPLE_COST_CENTERS,
    )
    from tallybridge.models.master import (
        TallyLedger, TallyGroup, TallyStockItem,
        TallyUnit, TallyStockGroup, TallyCostCenter,
    )
    from tallybridge.models.voucher import TallyVoucher, TallyVoucherEntry
    # Build model instances from sample data tuples and upsert them.
    # Populate: groups, ledgers, units, stock_groups, stock_items,
    #           cost_centers, vouchers (with ledger entries).
    # ...
    return tmp_db

@pytest.fixture
def tally_query(populated_db):
    """TallyQuery ready to use over populated test database."""
    from tallybridge.query import TallyQuery
    return TallyQuery(populated_db)

@pytest.fixture
def tally_connection(mock_tally_server):
    """TallyConnection pointing at the mock server."""
    from tallybridge.config import TallyBridgeConfig
    from tallybridge.connection import TallyConnection
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_tally_server.port,
    )
    return TallyConnection(config)
```

### §11c — tests/test_integration.py

Full end-to-end flow test:
1. Use `tally_connection` (→ mock server) + `tmp_db` + real `TallyXMLParser`
2. Create `TallySyncEngine(connection, db, parser)`
3. Call `await engine.sync_all()`
4. Assert all `SyncResult.success == True`
5. Assert records_synced > 0 for: ledger, group, unit, stock_group, stock_item, cost_center, voucher
6. Create `TallyQuery(db)` and call `get_daily_digest()`
7. Assert `digest.total_sales > 0`
8. Assert `len(get_receivables()) > 0`
9. Assert `get_stock_aging()` returns items with correct aging buckets
10. Assert cancelled voucher (guid-v-006) is excluded from `get_daily_digest().total_sales`

---

## §12 — __init__.py (Public API Contract)

**File:** `src/tallybridge/__init__.py`

This is the stable contract. Do not remove or rename exports without a major version bump.

```python
from tallybridge.config import TallyBridgeConfig, get_config
from tallybridge.connection import TallyConnection
from tallybridge.cache import TallyCache
from tallybridge.sync import TallySyncEngine, SyncResult
from tallybridge.query import TallyQuery
from tallybridge.parser import TallyXMLParser
from tallybridge.models.master import (
    TallyLedger, TallyGroup, TallyStockItem,
    TallyUnit, TallyStockGroup, TallyCostCenter,
)
from tallybridge.models.voucher import TallyVoucher, TallyVoucherEntry
from tallybridge.models.report import (
    DailyDigest, OutstandingBill, TrialBalanceLine, StockAgingLine,
)
from tallybridge.exceptions import (
    TallyConnectionError,
    TallyDataError,
    TallySyncError,
    TallyBridgeCacheError,
)

def connect(
    tally_host: str = "localhost",
    tally_port: int = 9000,
    db_path: str = "tallybridge.duckdb",
    company: str | None = None,
) -> TallyQuery:
    """Connect to TallyBridge: sync fresh data from Tally, return TallyQuery.
    
    The simplest possible entry point for new users.
    
    Example:
        import tallybridge
        q = tallybridge.connect()
        digest = q.get_daily_digest()
        print(f"Today's sales: ₹{digest.total_sales:,.0f}")
    
    Raises:
        TallyConnectionError: If TallyPrime is not running.
    """
    config = TallyBridgeConfig(
        tally_host=tally_host,
        tally_port=tally_port,
        db_path=db_path,
        tally_company=company,
    )
    cache = TallyCache(db_path)
    cache.initialize()
    # Sync is done synchronously for the convenience function
    # Advanced users should use TallySyncEngine directly for async control
    import asyncio
    connection = TallyConnection(config)
    parser = TallyXMLParser()
    engine = TallySyncEngine(connection, cache, parser)
    asyncio.run(engine.sync_all())
    return TallyQuery(cache)


__version__ = "0.1.0"
__all__ = [
    "connect",
    "__version__",
    "TallyBridgeConfig", "get_config",
    "TallyConnection",
    "TallyCache",
    "TallySyncEngine", "SyncResult",
    "TallyQuery",
    "TallyXMLParser",
    "TallyLedger", "TallyGroup", "TallyStockItem",
    "TallyUnit", "TallyStockGroup", "TallyCostCenter",
    "TallyVoucher", "TallyVoucherEntry",
    "DailyDigest", "OutstandingBill", "TrialBalanceLine", "StockAgingLine",
    "TallyConnectionError", "TallyDataError",
    "TallySyncError", "TallyBridgeCacheError",
]
```

---

## §13 — recipes/

**Four standalone scripts** runnable as `python recipes/<name>.py`. Each reads config from `.env`.
Each must fail gracefully (print a clear message and exit 0) when Tally is not connected.

### recipes/daily_digest.py

- Calls `tallybridge.connect()` → `q.get_daily_digest()`
- Prints a Rich-formatted summary table to console
- Optionally posts to WhatsApp via WhatsApp Business Cloud API
- Config via env: `WA_PHONE_NUMBER_ID`, `WA_TOKEN`, `WA_RECIPIENT_NUMBER`

### recipes/overdue_receivables.py

- Calls `q.get_receivables(overdue_only=True, min_days_overdue=30)`
- Generates an HTML email report and sends via `smtplib`
- Config via env: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `REPORT_TO`

### recipes/gst_mismatch_alert.py

- Calls `q.get_gst_summary(from_date, to_date)`
- Fetches all sales vouchers for the period and checks for missing GSTINs
- Flags parties where GSTIN is missing but invoice amount > ₹50,000
- Prints actionable report: "Party X: 3 invoices totalling ₹1,45,000 — GSTIN missing"

### recipes/anomaly_detector.py

- Fetches last 30 days of vouchers via `q.get_vouchers(from_date=..., to_date=...)`
- Flags: transactions > 2× the 30-day daily average for that voucher type
- Flags: round-number payments that are exact multiples of ₹50,000
- Flags: empty narration on vouchers > ₹10,000
- Prints each flag with: date, voucher number, amount, reason

Each recipe: clear module-level docstring, inline comments explaining each step, no tests required.
