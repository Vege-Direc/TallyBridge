# TallyBridge

Connect TallyPrime to DuckDB and AI via MCP.

TallyBridge syncs your TallyPrime accounting data to a local DuckDB database and
exposes it via the MCP protocol so AI assistants (Claude, GPT, etc.) can query it
in plain English.

## Quickstart

```bash
pip install tallybridge
```

```python
import tallybridge

q = tallybridge.connect()
digest = q.get_daily_digest()
print(f"Today's sales: ₹{digest.total_sales:,.0f}")
```

## CLI

```bash
tallybridge init          # Interactive setup wizard
tallybridge sync          # One-time sync
tallybridge status        # Show sync status
tallybridge doctor        # Diagnostic checks
tallybridge mcp           # Start MCP server (stdio)
```

## MCP Integration

Add to your `claude_desktop_config.json`:

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

## Requirements

- Python 3.11+
- TallyPrime running with HTTP server enabled (port 9000)

## License

MIT
