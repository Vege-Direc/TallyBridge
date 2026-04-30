# TallyBridge

Sync TallyPrime to a local database. Query it from Python or AI.

TallyBridge pulls your accounting data out of TallyPrime and into a local DuckDB
file. Once synced, **TallyPrime can be closed** — all queries run against the
local database. It also exposes an MCP server so AI assistants (Claude, Cursor)
can query your data in plain English.

## Quick Start

### 1. Install

```bash
pip install tallybridge
```

### 2. Enable TallyPrime HTTP server

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

This fetches all ledgers, groups, stock items, vouchers, godowns, and more into a local
`tallybridge.duckdb` file. **You only need TallyPrime running during sync.** After
that, close TallyPrime — queries work offline against the local database.

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

## CLI

```bash
tallybridge init              # Interactive setup wizard
tallybridge sync              # Sync data from TallyPrime
tallybridge sync --full       # Force full re-sync
tallybridge sync --watch      # Continuous sync every N minutes
tallybridge status            # Show sync status per entity
tallybridge doctor            # Run diagnostic checks
tallybridge config show       # Print current configuration
tallybridge config set KEY VALUE  # Set a config value
tallybridge mcp               # Start MCP server (for AI assistants)
tallybridge mcp --http        # Start MCP server with HTTP transport
tallybridge serve             # Start HTTP API bridge for BI tools
tallybridge serve --port 8080 # Start on custom port
tallybridge --version         # Show version
```

## Python API

```python
import tallybridge

q = tallybridge.connect()

# Business summaries
q.get_daily_digest()                        # Sales, purchases, balances
q.get_receivables()                         # Outstanding sales invoices
q.get_payables()                            # Outstanding purchase invoices
q.get_gst_summary(from_date, to_date)      # GST collected, ITC, net liability
q.get_sales_summary(from_date, to_date, group_by="party")

# Ledger queries
q.get_ledger_balance("Cash")                # Closing balance of any ledger
q.get_party_outstanding("Sharma Trading Co")

# Inventory
q.get_stock_summary()                       # All stock items with quantities
q.get_low_stock_items(threshold=5)          # Items below threshold
q.get_stock_aging()                         # How long stock has been sitting

# GST Reports
q.fetch_gstr1(from_date, to_date)              # GSTR-1 outward supply report
q.fetch_gstr3b(from_date, to_date)              # GSTR-3B summary return
q.fetch_gstr9(from_date, to_date)               # GSTR-9 annual return
q.reconcile_itc(from_date, to_date)             # GSTR-2A ITC reconciliation

# Search
q.search(query="sharma", limit=10)              # Search ledgers, parties, narrations
```

## Configuration

Set via environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `TALLYBRIDGE_TALLY_HOST` | `localhost` | TallyPrime host |
| `TALLYBRIDGE_TALLY_PORT` | `9000` | TallyPrime HTTP port |
| `TALLYBRIDGE_TALLY_COMPANY` | *(auto-detect)* | Company name in TallyPrime |
| `TALLYBRIDGE_TALLY_ENCODING` | `utf-8` | Request encoding (`utf-8` or `utf-16`) |
| `TALLYBRIDGE_TALLY_EXPORT_FORMAT` | `auto` | Export format: `auto`, `xml`, or `json` (auto uses JSONEx on TallyPrime 7.0+) |
| `TALLYBRIDGE_DB_PATH` | `tallybridge.duckdb` | Local database file path |
| `TALLYBRIDGE_SYNC_FREQUENCY_MINUTES` | `5` | Sync interval in `--watch` mode |
| `TALLYBRIDGE_VOUCHER_BATCH_SIZE` | `5000` | Vouchers fetched per batch (100–10000) |
| `TALLYBRIDGE_STRICT_STATUS` | `false` | Treat STATUS=0 as error (Tally semantics) |
| `TALLYBRIDGE_ALLOW_WRITES` | `false` | Enable import/write-back to TallyPrime (requires explicit opt-in) |
| `TALLYBRIDGE_MCP_API_KEY` | *(none)* | Bearer token for MCP HTTP transport auth |
| `TALLYBRIDGE_LOG_LEVEL` | `INFO` | Logging level |

Example `.env`:

```env
TALLYBRIDGE_TALLY_HOST=localhost
TALLYBRIDGE_TALLY_PORT=9000
TALLYBRIDGE_TALLY_COMPANY=My Company Pvt Ltd
```

## Testing with TallyPrime

If you have access to a TallyPrime installation:

1. **Open TallyPrime** and load a company with some data
2. **Enable HTTP server** (F1 → Settings → Connectivity → Server, port 9000)
3. **Run diagnostics**:

```bash
tallybridge doctor
```

4. **Sync and verify**:

```bash
tallybridge sync
tallybridge status
```

5. **Query from Python**:

```python
import tallybridge
q = tallybridge.connect()
print(q.get_daily_digest())
print(q.search("cash"))
```

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
                           │    ┌─────┴──────┐      │
                           │    │            │      │
                           │  TallyQuery   MCP Server
                           │  (Python)    (for AI)   │
                           └──────────────────────┘
```

- **Sync** pulls data from TallyPrime via its HTTP API (XML or JSON/JSONEx on TallyPrime 7.0+)
- **Cache** stores everything in a local DuckDB file — works offline, with content hash drift detection and sync error tracking
- **Query** reads from the local file — TallyPrime doesn't need to be running
- **Import** write back to TallyPrime (masters and vouchers) when `TALLYBRIDGE_ALLOW_WRITES=true`
- **MCP** exposes the same data to AI assistants via stdio or HTTP transport (20 tools)

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

## Multi-Currency Vouchers

TallyVoucher and TallyVoucherEntry include optional currency fields for import/export businesses:

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
`None` by default for INR-only vouchers. The sync pipeline automatically stores these
fields when present in Tally data.

For TallyPrime 7.0+, use JSON import:

```python
conn._detected_version = TallyProduct.PRIME_7
msg = TallyConnection.build_ledger_json("New Supplier", "Sundry Creditors")
result = asyncio.run(conn.import_masters_json(msg))
```

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
- **Power BI**: Install DuckDB ODBC driver, connect to `tallybridge.duckdb`
- **Metabase**: Use native DuckDB driver
- **Superset**: Use DuckDB connector
- **Excel**: ODBC or export via `COPY table TO 'file.csv'`
- **Any HTTP client**: Use `tallybridge serve` for a REST API (requires `pip install tallybridge[serve]`)

```bash
pip install tallybridge[serve]
tallybridge serve --port 8080
# Then query: curl http://localhost:8080/views/v_sales_summary
# Or POST SQL: curl -X POST http://localhost:8080/query -d '{"sql":"SELECT * FROM mst_ledger"}'
```

## Compatibility

| Product | Support |
|---|---|
| TallyPrime 7.0+ | Full support (JSON/JSONEx API, import, base64 encoding) |
| TallyPrime 4.0+ | Primary target (XML sync, Connected GST) |
| TallyPrime 1.x–3.x | Supported (XML only) |
| Tally.ERP 9 | Best-effort (LEDGERENTRIES.LIST fallback) |

TallyBridge auto-detects your Tally version on first sync.

## Development

```bash
git clone https://github.com/nicholasgriffintn/tallybridge.git
cd tallybridge
uv sync --extra dev
uv run pytest
```

No TallyPrime installation needed — tests use a mock HTTP server.

## License

MIT
