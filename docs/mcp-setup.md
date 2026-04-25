# MCP Setup Guide

## Configuring TallyBridge as an MCP Server for Claude Desktop

TallyBridge includes an MCP (Model Context Protocol) server that allows AI assistants like Claude to query your Tally data directly.

### Step 1: Install TallyBridge

```bash
pip install tallybridge
```

Or if using uv:

```bash
uv pip install tallybridge
```

### Step 2: Configure Claude Desktop

Edit your Claude Desktop configuration file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add the TallyBridge MCP server:

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
      ],
      "env": {
        "TALLYBRIDGE_TALLY_HOST": "localhost",
        "TALLYBRIDGE_TALLY_PORT": "9000",
        "TALLYBRIDGE_TALLY_COMPANY": ""
      }
    }
  }
}
```

If you installed TallyBridge globally with pip, replace the `uv` command:

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

### Step 3: Set Environment Variables

You can set environment variables either in the `claude_desktop_config.json` `env` block (as shown above) or in a `.env` file in your project directory:

```env
TALLYBRIDGE_TALLY_HOST=localhost
TALLYBRIDGE_TALLY_PORT=9000
TALLYBRIDGE_TALLY_COMPANY=Your Company Name
```

### Step 4: Restart Claude Desktop

After updating the configuration, fully quit and restart Claude Desktop for the changes to take effect.

### Step 5: Verify the Connection

In Claude Desktop, ask a question that triggers TallyBridge, for example:

> "What were today's total sales in Tally?"

If the MCP server is configured correctly, Claude will invoke the TallyBridge tools and return data from TallyPrime.

### Available MCP Tools

| Tool | Description |
|---|---|
| `get_daily_digest` | Business summary for a given date |
| `get_receivables` | Outstanding sales invoices |
| `get_payables` | Outstanding purchase invoices |
| `get_trial_balance` | Trial balance for a period |
| `get_gst_summary` | GST summary for a period |
| `get_stock_summary` | Stock item quantities and values |
| `search` | Search across ledgers, vouchers, and parties |

### Troubleshooting

| Problem | Solution |
|---|---|
| MCP server not found | Verify the `command` path is correct and `tallybridge-mcp` is on your PATH. |
| Connection errors | Ensure TallyPrime is running with the HTTP server enabled on port 9000. See [tally-setup.md](tally-setup.md). |
| Claude cannot see tools | Restart Claude Desktop after config changes. Check the `claude_desktop_config.json` syntax. |
| Permission denied | On macOS/Linux, ensure the command is executable (`chmod +x`). |
