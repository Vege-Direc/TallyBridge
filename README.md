<div align="center">

# TallyBridge

**Sync TallyPrime to a local database. Query it from Python or AI.**

[![Test](https://github.com/nicholasgriffintn/tallybridge/actions/workflows/test.yml/badge.svg)](https://github.com/nicholasgriffintn/tallybridge/actions/workflows/test.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

---

TallyBridge pulls your accounting data out of TallyPrime and into a local DuckDB
file. Once synced, **TallyPrime can be closed** — all queries run against the
local database. It also exposes an MCP server so AI assistants (Claude, Cursor)
can query your data in plain English.

## Highlights

- **Offline-first** — TallyPrime only needs to run during sync
- **Incremental sync** — AlterID-based, only fetches what changed
- **22 MCP tools** — Query your accounts from Claude, Cursor, or any AI
- **GST compliance** — GSTR-1, GSTR-3B, GSTR-9, ITC reconciliation
- **Write-back** — Create ledgers and vouchers from Python or AI
- **BI integration** — Pre-built views for Power BI, Metabase, Superset
- **Data export** — CSV, Excel, JSON with audit logging
- **TallyPrime 7.0** — Auto-detects and uses JSON/JSONEx when available
- **Tally.ERP 9 compatible** — XML fallback for all versions

---

## Quick Start

### 1. Install

```bash
pip install tallybridge
```

### 2. Enable TallyPrime HTTP Server

1. Open TallyPrime and load your company
2. Press **F1** → **Settings** → **Connectivity**
3. Set **TallyPrime acts as** → **Server**, **Port** → **9000**
4. Save

<details>
<summary>Can't find the setting?</summary>

On some TallyPrime versions: press **F12** → **Product & Features** → **Advanced** → check **Enable ODBC/HTTP**. The HTTP server port is configured under **F1** → **Settings** → **Connectivity**.

See [docs/tally-setup.md](docs/tally-setup.md) for full instructions.
</details>

### 3. Sync

```bash
tallybridge sync
```

This fetches all ledgers, groups, stock items, vouchers, and more into a local
`tallybridge.duckdb` file. **You only need TallyPrime running during sync.**
After that, close TallyPrime — queries work offline.

### 4. Query from Python

```python
import tallybridge

q = tallybridge.connect()
digest = q.get_daily_digest()
print(f"Today's sales: {digest.total_sales:,.0f}")
```

### 5. Connect to AI (optional)

Add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "tallybridge": {
      "command": "tallybridge-mcp"
    }
  }
}
```

See [docs/mcp-setup.md](docs/mcp-setup.md) for full details.

---

## CLI Reference

```bash
# Setup & sync
tallybridge init                        # Interactive setup wizard
tallybridge sync                        # Sync data from TallyPrime
tallybridge sync --full                 # Force full re-sync
tallybridge sync --watch                # Continuous sync every N minutes
tallybridge status                      # Show sync status per entity
tallybridge doctor                      # Run diagnostic checks

# Configuration
tallybridge config show                 # Print current configuration
tallybridge config set KEY VALUE        # Set a config value

# Data export
tallybridge export csv --table ledgers  # Export table to CSV
tallybridge export csv --table vouchers --where "date >= '2025-01-01'"
tallybridge export excel                # Export all tables to Excel
tallybridge export json --table stock_items

# Reports
tallybridge report generate --type daily_digest
tallybridge report generate --type gst_summary --from 2025-01-01 --to 2025-03-31

# MCP & API
tallybridge mcp                         # Start MCP server (stdio)
tallybridge mcp --http                  # Start MCP server with HTTP transport
tallybridge serve                       # Start HTTP API bridge for BI tools
tallybridge serve --port 8080           # Start on custom port

# Other
tallybridge --version                   # Show version
```

---

## Python API

### Business Summaries

```python
import tallybridge

q = tallybridge.connect()

q.get_daily_digest()                            # Sales, purchases, balances
q.get_receivables()                             # Outstanding sales invoices
q.get_payables()                                # Outstanding purchase invoices
q.get_gst_summary(from_date, to_date)           # GST collected, ITC, net liability
q.get_sales_summary(from_date, to_date, group_by="party")
```

### Ledger & Account Queries

```python
q.get_ledger_balance("Cash")                    # Closing balance
q.get_party_outstanding("Sharma Trading Co")    # Full party position
q.get_balance_sheet(to_date="2025-03-31")       # Balance sheet
q.get_profit_loss(from_date, to_date)           # Profit & Loss
q.get_ledger_account("Cash", from_date, to_date)  # Voucher-level GL
```

### Inventory

```python
q.get_stock_summary()                           # All stock items with quantities
q.get_low_stock_items(threshold=5)              # Items below threshold
q.get_stock_aging()                             # How long stock has been sitting
q.get_stock_item_account("Widget A", from_date, to_date)  # Stock movements
```

### GST Reports

```python
q.fetch_gstr1(from_date, to_date)               # GSTR-1 outward supply report
q.fetch_gstr3b(from_date, to_date)              # GSTR-3B summary return
q.fetch_gstr9(from_date, to_date)               # GSTR-9 annual return
q.reconcile_itc(from_date, to_date)             # GSTR-2A ITC reconciliation
```

### Search

```python
q.search(query="sharma", limit=10)              # Search ledgers, parties, narrations
```

### E-Invoice & E-Way Bill

```python
q.get_einvoice_summary(from_date, to_date)      # IRN coverage and missing invoices
q.get_eway_bill_summary(from_date, to_date)     # Active, expired, expiring bills
```

### Data Export

```python
from tallybridge.export import DataExporter
from tallybridge.cache import TallyCache

cache = TallyCache("tallybridge.duckdb")
exporter = DataExporter(cache)

# CSV export with filters
exporter.export_csv("ledgers", path="ledgers.csv")
exporter.export_csv("vouchers", where="date >= '2025-01-01'", limit=1000)

# Excel (multi-sheet) — requires pip install tallybridge[excel]
exporter.export_excel(path="tally_data.xlsx")

# JSON
exporter.export_json("stock_items", path="stock.json")

# Memory-efficient chunked export for large datasets
exporter.export_csv_chunked("vouchers", path="vouchers.csv", chunk_size=50000)
```

### Audit Log

```python
# All write operations are automatically logged
q.get_audit_log(from_date="2025-01-01", operation="create")
q.get_audit_log(entity_type="voucher")
```

---

## TallyBridge Unified Client

The `TallyBridge` class provides sync, query, validation, and write-back in one object:

```python
import asyncio
import tallybridge

async def main():
    async with tallybridge.TallyBridge() as tb:
        # Sync data from TallyPrime
        await tb.sync()

        # Query (proxied to TallyQuery)
        digest = tb.get_daily_digest()
        balance = tb.get_ledger_balance("Cash")

        # Pre-write validation
        v = await tb.validate_voucher(
            "Sales", "20250101",
            [{"ledger_name": "Sales", "amount": "-5000"},
             {"ledger_name": "Cash", "amount": "5000"}],
        )
        print(f"Valid: {v.valid}, Errors: {v.errors}")

        # Create with automatic validation
        await tb.create_ledger("New Customer", "Sundry Debtors")
        await tb.create_voucher(
            "Sales", "20250101",
            [{"ledger_name": "Sales", "amount": "-5000"},
             {"ledger_name": "Cash", "amount": "5000"}],
        )

        # Skip validation (e.g. for batch imports)
        await tb.create_voucher("Sales", "20250101", entries, validate=False)

asyncio.run(main())
```

---

## Import / Write-Back

Create ledgers and vouchers in TallyPrime from Python:

```python
import asyncio
from tallybridge import TallyConnection, TallyBridgeConfig

# Set TALLYBRIDGE_ALLOW_WRITES=true in your environment
config = TallyBridgeConfig(allow_writes=True)
conn = TallyConnection(config)

# Create a ledger (XML — works on all versions)
xml = TallyConnection.build_ledger_xml("New Customer", "Sundry Debtors", "0")
result = asyncio.run(conn.import_masters(xml))
print(f"Created: {result.created}, Errors: {result.errors}")

# Create a voucher
xml = TallyConnection.build_voucher_xml(
    "Sales", "20250101",
    [{"ledger_name": "Sales", "amount": "-5000"},
     {"ledger_name": "Cash", "amount": "5000"}],
    narration="Cash sale",
)
result = asyncio.run(conn.import_vouchers(xml))
print(f"Created: {result.created}")

# Cancel a voucher
xml = TallyConnection.build_cancel_voucher_xml("guid-abc-123", "Sales")
result = asyncio.run(conn.import_vouchers(xml))

asyncio.run(conn.close())
```

---

## Multi-Currency Vouchers

```python
from tallybridge import TallyVoucher, TallyVoucherEntry

v = TallyVoucher(
    voucher_type="Sales",
    date="20250101",
    currency="USD",
    forex_amount="100.00",
    exchange_rate="83.50",
    base_currency_amount="8350.00",
    entries=[
        TallyVoucherEntry(
            ledger_name="Sales",
            amount="-8350.00",
            currency="USD",
            forex_amount="100.00",
            exchange_rate="83.50",
        ),
    ],
)
```

Currency fields (`currency`, `forex_amount`, `exchange_rate`, `base_currency_amount`) are
`None` by default for INR-only vouchers.

For TallyPrime 7.0+, use JSON import:

```python
conn._detected_version = TallyProduct.PRIME_7
msg = TallyConnection.build_ledger_json("New Supplier", "Sundry Creditors")
result = asyncio.run(conn.import_masters_json(msg))
```

---

## Configuration

Set via environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `TALLYBRIDGE_TALLY_HOST` | `localhost` | TallyPrime host |
| `TALLYBRIDGE_TALLY_PORT` | `9000` | TallyPrime HTTP port |
| `TALLYBRIDGE_TALLY_COMPANY` | *(auto-detect)* | Company name in TallyPrime |
| `TALLYBRIDGE_TALLY_ENCODING` | `utf-8` | Request encoding (`utf-8` or `utf-16`) |
| `TALLYBRIDGE_TALLY_EXPORT_FORMAT` | `auto` | Export format: `auto`, `xml`, or `json` |
| `TALLYBRIDGE_DB_PATH` | `tallybridge.duckdb` | Local database file path |
| `TALLYBRIDGE_SYNC_FREQUENCY_MINUTES` | `5` | Sync interval in `--watch` mode |
| `TALLYBRIDGE_VOUCHER_BATCH_SIZE` | `5000` | Vouchers fetched per batch (100–5000) |
| `TALLYBRIDGE_STRICT_STATUS` | `false` | Treat STATUS=0 as error |
| `TALLYBRIDGE_ALLOW_WRITES` | `false` | Enable write-back to TallyPrime |
| `TALLYBRIDGE_MCP_API_KEY` | *(none)* | Bearer token for MCP HTTP transport |
| `TALLYBRIDGE_QUERY_CACHE_TTL` | `300` | Query result cache TTL in seconds |
| `TALLYBRIDGE_SLOW_QUERY_THRESHOLD` | `1.0` | Log queries slower than this (seconds) |
| `TALLYBRIDGE_EXPORT_CHUNK_SIZE` | `5000` | Rows per chunk for chunked export |
| `TALLYBRIDGE_LOG_LEVEL` | `INFO` | Logging level |

Example `.env`:

```env
TALLYBRIDGE_TALLY_HOST=localhost
TALLYBRIDGE_TALLY_PORT=9000
TALLYBRIDGE_TALLY_COMPANY=My Company Pvt Ltd
```

---

## BI Integration

TallyBridge creates 5 pre-built SQL views in DuckDB for BI tool connections:

| View | Description |
|---|---|
| `v_sales_summary` | Sales and credit note vouchers with amounts |
| `v_receivables` | Outstanding receivables with overdue days |
| `v_gst_summary` | GST ledger totals by date |
| `v_stock_summary` | Stock items with quantities and values |
| `v_party_position` | Party receivable/payable classification |

Connect from BI tools:
- **Power BI** — DuckDB ODBC driver
- **Metabase** — Native DuckDB driver
- **Superset** — DuckDB connector
- **Excel** — ODBC or `tallybridge export csv`
- **Any HTTP client** — `tallybridge serve` REST API (requires `pip install tallybridge[serve]`)

```bash
pip install tallybridge[serve]
tallybridge serve --port 8080
# GET  http://localhost:8080/views/v_sales_summary
# POST http://localhost:8080/query  {"sql": "SELECT * FROM mst_ledger"}
```

See [docs/bi-integration.md](docs/bi-integration.md) for detailed connection guides.

---

## MCP Tools (22 read-only + 3 write = 25 total)

### Read-Only Tools

| Tool | Description |
|---|---|
| `get_tally_digest` | Complete business summary |
| `get_ledger_balance` | Closing balance of any ledger |
| `get_receivables` | Outstanding sales invoices |
| `get_payables` | Outstanding purchase invoices |
| `get_party_outstanding` | Full position with one party |
| `get_sales_summary` | Sales by day/week/month/party |
| `get_gst_summary` | GST collected, ITC, net liability |
| `search_tally` | Search ledgers, parties, narrations |
| `get_sync_status` | Last sync time and record counts |
| `get_low_stock` | Items at or below quantity threshold |
| `get_stock_aging` | Stock aging by day buckets |
| `get_cost_center_summary` | Income/expense by cost centre |
| `get_balance_sheet` | Balance sheet grouped by assets/liabilities |
| `get_profit_loss` | P&L grouped by income/expense |
| `get_ledger_account` | Voucher-level general ledger |
| `get_stock_item_account` | Quantity movements for a stock item |
| `query_tally_data` | Run custom SQL on local cache |
| `get_sync_errors` | Recent sync errors |
| `get_gstr1` | GSTR-1 outward supply data |
| `reconcile_itc` | ITC reconciliation (GSTR-2A) |
| `get_gstr9` | GSTR-9 annual return data |
| `get_einvoice_status` | E-invoice IRN coverage |
| `get_eway_bill_status` | E-Way Bill status |
| `export_data` | Export cached data as CSV or JSON |
| `get_audit_log` | Audit log of write operations |

### Write Tools (requires `TALLYBRIDGE_ALLOW_WRITES=true`)

> **Note:** Write tools are available via the Python API (`TallyBridge` client class)
> and are planned for MCP exposure in a future release.

| Tool | Description |
|---|---|
| `create_ledger` | Create a new ledger |
| `create_voucher` | Create a new voucher |
| `cancel_voucher` | Cancel a voucher by GUID |

---

## Compatibility

| Product | Support |
|---|---|
| TallyPrime 7.0+ | Full support (JSON/JSONEx API, import, base64 encoding) |
| TallyPrime 4.0+ | Primary target (XML sync, Connected GST) |
| TallyPrime 1.x–3.x | Supported (XML only) |
| Tally.ERP 9 | Best-effort (LEDGERENTRIES.LIST fallback) |

TallyBridge auto-detects your Tally version on first sync. See
[docs/tally-setup.md](docs/tally-setup.md) for the full feature compatibility matrix.

---

## How It Works

```
  TallyPrime (port 9000)          Your Machine
  ┌─────────────────┐     ┌──────────────────────┐
  │  Accounting data │────→│  TallySyncEngine      │
  │  (XML/JSON HTTP) │     │  TallyXMLParser       │
  └─────────────────┘     │  TallyJSONParser       │
                           │          │             │
                           │          ▼             │
                           │  tallybridge.duckdb    │
                           │  (local, offline)      │
                           │          │             │
                           │    ┌─────┼──────┐      │
                           │    │     │      │      │
                           │  Query  MCP   HTTP API │
                           │ (Python) (AI)  (BI)    │
                           └──────────────────────┘
```

1. **Sync** — Pull data from TallyPrime via HTTP (XML or JSON/JSONEx on 7.0+)
2. **Cache** — Store in local DuckDB with content hash drift detection
3. **Query** — Read from local file — TallyPrime doesn't need to be running
4. **Import** — Write back to TallyPrime when `TALLYBRIDGE_ALLOW_WRITES=true`
5. **MCP** — Expose data to AI assistants via stdio or HTTP (24 tools)
6. **Export** — CSV, Excel, JSON with audit logging

---

## Development

```bash
git clone https://github.com/nicholasgriffintn/tallybridge.git
cd tallybridge
uv sync --extra dev
uv run pytest
```

No TallyPrime installation needed — tests use a mock HTTP server.

### Optional Dependencies

```bash
pip install tallybridge[serve]    # FastAPI HTTP API bridge
pip install tallybridge[excel]    # Excel export (openpyxl)
pip install tallybridge[cloud]    # Supabase cloud sync (future)
```

---

## License

[MIT](LICENSE)
