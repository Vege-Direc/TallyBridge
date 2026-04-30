# MCP Setup Guide

Connect TallyBridge to AI assistants via the Model Context Protocol (MCP).

## Installation

```bash
pip install tallybridge
```

## Configure Claude Desktop

Edit your Claude Desktop configuration file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

### Basic (stdio)

```json
{
  "mcpServers": {
    "tallybridge": {
      "command": "tallybridge-mcp",
      "env": {
        "TALLYBRIDGE_TALLY_HOST": "localhost",
        "TALLYBRIDGE_TALLY_PORT": "9000",
        "TALLYBRIDGE_TALLY_COMPANY": ""
      }
    }
  }
}
```

### Using uv with a local clone

```json
{
  "mcpServers": {
    "tallybridge": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/TallyBridge",
        "run",
        "tallybridge-mcp"
      ]
    }
  }
}
```

### Using the CLI subcommand

```json
{
  "mcpServers": {
    "tallybridge": {
      "command": "tallybridge",
      "args": ["mcp"]
    }
  }
}
```

### With write-back enabled

```json
{
  "mcpServers": {
    "tallybridge": {
      "command": "tallybridge-mcp",
      "env": {
        "TALLYBRIDGE_TALLY_HOST": "localhost",
        "TALLYBRIDGE_TALLY_PORT": "9000",
        "TALLYBRIDGE_ALLOW_WRITES": "true"
      }
    }
  }
}
```

> **Warning:** Enabling write-back allows AI assistants to modify data in TallyPrime. Use with caution and review all import operations carefully.

## Environment Variables

You can set environment variables either in the `env` block of your config or in a `.env` file in your project directory:

```env
TALLYBRIDGE_TALLY_HOST=localhost
TALLYBRIDGE_TALLY_PORT=9000
TALLYBRIDGE_TALLY_COMPANY=Your Company Name
```

## Verify the Connection

After updating the configuration, fully quit and restart Claude Desktop. Then ask a question that triggers TallyBridge:

> "What were today's total sales in Tally?"

If the MCP server is configured correctly, Claude will invoke the TallyBridge tools and return data from TallyPrime.

## Available MCP Tools

### Business Overview

| Tool | Description | Key Parameters |
|---|---|---|
| `get_tally_digest` | Complete business summary: sales, purchases, balances, overdue | `date` (optional) |
| `get_sync_status` | Last sync time and record counts | — |
| `get_sync_errors` | Recent sync errors with GUIDs and messages | `entity_type`, `limit` |

### Ledger & Account

| Tool | Description | Key Parameters |
|---|---|---|
| `get_ledger_balance` | Closing balance of any ledger | `ledger_name` (required), `date` |
| `get_party_outstanding` | Full receivable/payable position with one party | `party_name` (required) |
| `get_balance_sheet` | Balance sheet grouped by assets/liabilities | `to_date` |
| `get_profit_loss` | P&L grouped by income/expense | `from_date`, `to_date` |
| `get_ledger_account` | Voucher-level general ledger | `ledger_name`, `from_date`, `to_date` |

### Sales & Purchases

| Tool | Description | Key Parameters |
|---|---|---|
| `get_sales_summary` | Sales by day/week/month/party/item | `from_date`, `to_date`, `group_by` |
| `get_receivables` | Outstanding sales invoices | `overdue_only`, `min_days_overdue` |
| `get_payables` | Outstanding purchase invoices | `overdue_only` |

### GST & Compliance

| Tool | Description | Key Parameters |
|---|---|---|
| `get_gst_summary` | GST collected, ITC, net liability | `from_date`, `to_date` |
| `get_gstr1` | GSTR-1 outward supply data | `from_date`, `to_date` |
| `reconcile_itc` | ITC reconciliation (GSTR-2A vs purchases) | `from_date`, `to_date` |
| `get_gstr9` | GSTR-9 annual return data | `from_date`, `to_date` |
| `get_einvoice_status` | E-invoice IRN coverage and missing invoices | `from_date`, `to_date` |
| `get_eway_bill_status` | E-Way Bill active, expired, expiring | `from_date`, `to_date` |

### Inventory

| Tool | Description | Key Parameters |
|---|---|---|
| `get_low_stock` | Items at or below quantity threshold | `threshold` |
| `get_stock_aging` | Stock aging by day buckets | `date`, `bucket_days` |
| `get_stock_item_account` | Quantity movements for a stock item | `item_name`, `from_date`, `to_date` |

### Cost Centres

| Tool | Description | Key Parameters |
|---|---|---|
| `get_cost_center_summary` | Income/expense breakdown by cost centre | `from_date`, `to_date`, `cost_center_name` |

### Data & Export

| Tool | Description | Key Parameters |
|---|---|---|
| `search_tally` | Search ledgers, parties, voucher narrations | `query`, `limit` |
| `query_tally_data` | Run custom SQL on local cache (read-only) | `sql`, `limit` |
| `export_data` | Export cached data as CSV or JSON string | `table`, `format`, `columns`, `where`, `limit` |
| `get_audit_log` | Audit log of write operations | `from_date`, `to_date`, `entity_type`, `operation` |

### Import / Write-Back (requires opt-in)

> **Note:** Write tools are currently available via the Python API
> (`TallyBridge` client class). MCP exposure is planned for a future release.
> These tools require `TALLYBRIDGE_ALLOW_WRITES=true`.

| Tool | Description | Key Parameters |
|---|---|---|
| `create_ledger` | Create a new ledger in TallyPrime | `name`, `parent_group`, `opening_balance` |
| `create_voucher` | Create a new voucher in TallyPrime | `voucher_type`, `date`, `entries`, `narration` |
| `cancel_voucher` | Cancel an existing voucher | `guid` |

## HTTP Transport

For remote/cloud deployments, use HTTP transport with an API key:

```bash
TALLYBRIDGE_MCP_TRANSPORT=http TALLYBRIDGE_MCP_API_KEY=your-secret-key tallybridge-mcp
```

All HTTP requests must include `Authorization: Bearer your-secret-key`.

## Troubleshooting

| Problem | Solution |
|---|---|
| MCP server not found | Verify `tallybridge-mcp` is on your PATH. Run `tallybridge-mcp --help` to check. |
| Connection errors | Ensure TallyPrime is running with HTTP server enabled on port 9000. See [tally-setup.md](tally-setup.md). |
| Claude cannot see tools | Restart Claude Desktop after config changes. Check `claude_desktop_config.json` syntax. |
| Permission denied | On macOS/Linux, ensure the command is executable (`chmod +x`). |
| HTTP auth failures | Verify the `Authorization: Bearer <key>` header matches your `TALLYBRIDGE_MCP_API_KEY`. |
| Write tools not appearing | Set `TALLYBRIDGE_ALLOW_WRITES=true` in the `env` block. |
