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

This fetches all ledgers, groups, stock items, vouchers, and more into a local
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

# Search
q.search(query="sharma", limit=10)          # Search ledgers, parties, narrations
```

## Configuration

Set via environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `TALLYBRIDGE_TALLY_HOST` | `localhost` | TallyPrime host |
| `TALLYBRIDGE_TALLY_PORT` | `9000` | TallyPrime HTTP port |
| `TALLYBRIDGE_TALLY_COMPANY` | *(auto-detect)* | Company name in TallyPrime |
| `TALLYBRIDGE_TALLY_ENCODING` | `utf-8` | Request encoding (`utf-8` or `utf-16`) |
| `TALLYBRIDGE_DB_PATH` | `tallybridge.duckdb` | Local database file path |
| `TALLYBRIDGE_SYNC_FREQUENCY_MINUTES` | `5` | Sync interval in `--watch` mode |
| `TALLYBRIDGE_VOUCHER_BATCH_SIZE` | `5000` | Vouchers fetched per batch (100–10000) |
| `TALLYBRIDGE_STRICT_STATUS` | `false` | Treat STATUS=0 as error (Tally semantics) |
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
  │  (XML over HTTP) │     │  TallyXMLParser       │
  └─────────────────┘     │          │             │
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

- **Sync** pulls data from TallyPrime via its HTTP API (XML format)
- **Cache** stores everything in a local DuckDB file — works offline, with content hash drift detection and sync error tracking
- **Query** reads from the local file — TallyPrime doesn't need to be running
- **MCP** exposes the same data to AI assistants via stdio or HTTP transport (13 tools)

## Compatibility

| Product | Support |
|---|---|
| TallyPrime 4.0+ | Primary target (Connected GST) |
| TallyPrime 1.x–3.x | Supported |
| Tally.ERP 9 | Best-effort (deprecated by Tally Solutions) |

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
