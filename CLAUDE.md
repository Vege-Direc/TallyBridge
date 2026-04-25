# CLAUDE.md

> Read this file completely before doing anything else.
> It tells you how to work, what to build, and where to find details.

---

## What This Project Is

TallyBridge is a Python library that syncs TallyPrime accounting data to a local DuckDB
database and exposes it via the MCP protocol so AI assistants can query it.

Target users: Indian CA firms and SMBs who want to ask Claude questions about their
Tally data in plain English.

---

## How You Work (Agent Loop)

Follow this loop for every task in TASKS.md:

```
1. Open TASKS.md — find the first unchecked item
2. Read the corresponding section in SPECS.md (each task references its section)
3. Implement the code exactly as specified
4. Run the verification command shown in TASKS.md for that task
5. If tests fail — fix the code and re-run; do not move on with failing tests
6. If stuck after 3 fix attempts — leave a comment `# STUCK: <reason>` and continue to next task
7. Check the box in TASKS.md: change `- [ ]` to `- [x]`
8. Commit with the message format: `feat(<module>): <one line description>`
9. Go back to step 1
```

**Never skip a failing test by disabling it or marking it xfail without a comment explaining why.**
**Never move to the next task while the current task's verification command is failing.**
**Always commit after each completed task — small, frequent commits.**

---

## Architecture

Six layers. Each layer only imports from layers below it — never upward.

```
┌──────────────────────────────────────────────────────┐
│  MCP Layer        src/tallybridge/mcp/               │  AI clients connect here
├──────────────────────────────────────────────────────┤
│  CLI Layer        src/tallybridge/cli.py             │  Humans interact here
├──────────────────────────────────────────────────────┤
│  Query Layer      src/tallybridge/query.py           │  Public API
├──────────────────────────────────────────────────────┤
│  Cache Layer      src/tallybridge/cache.py           │  DuckDB read/write
├──────────────────────────────────────────────────────┤
│  Sync Layer       src/tallybridge/sync.py            │  AlterID-based sync engine
├──────────────────────────────────────────────────────┤
│  Parser Layer     src/tallybridge/parser.py          │  Tally XML → Python models
├──────────────────────────────────────────────────────┤
│  Connection Layer src/tallybridge/connection.py      │  HTTP to Tally port 9000
└──────────────────────────────────────────────────────┘
         ↕
   src/tallybridge/models/       ← Pydantic models shared across all layers
   src/tallybridge/config.py     ← Config singleton imported by all layers
   src/tallybridge/exceptions.py ← Custom exceptions imported by all layers
```

---

## Repository Layout

```
tallybridge/
├── CLAUDE.md          ← This file (agent instructions)
├── SPECS.md           ← Full technical specifications (reference as needed)
├── TASKS.md           ← Ordered build checklist (check off as you complete)
├── pyproject.toml     ← Package config and dependencies
├── CHANGELOG.md
├── README.md
├── LICENSE
├── .gitignore
├── .github/
│   └── workflows/
│       ├── test.yml
│       └── publish.yml
├── src/tallybridge/
│   ├── __init__.py        ← Public API — stable contract, never break
│   ├── config.py
│   ├── exceptions.py
│   ├── connection.py
│   ├── parser.py
│   ├── cache.py
│   ├── sync.py
│   ├── query.py
│   ├── cli.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── master.py
│   │   ├── voucher.py
│   │   └── report.py
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   └── tools.py
│   └── cloud/
│       ├── __init__.py
│       └── supabase.py
├── tests/
│   ├── conftest.py        ← Shared fixtures — populated DB, mock Tally server
│   ├── mock_tally.py      ← HTTP server mimicking Tally's XML API
│   ├── test_exceptions.py
│   ├── test_config.py
│   ├── test_models.py
│   ├── test_connection.py
│   ├── test_parser.py
│   ├── test_cache.py
│   ├── test_sync.py
│   ├── test_query.py
│   ├── test_mcp.py
│   ├── test_cli.py
│   └── test_integration.py
├── recipes/
│   ├── daily_digest.py
│   ├── overdue_receivables.py
│   ├── gst_mismatch_alert.py
│   └── anomaly_detector.py
├── docs/
│   ├── quickstart.md
│   ├── tally-setup.md
│   └── mcp-setup.md
└── scripts/
    └── install.ps1
```

---

## Coding Standards (Non-Negotiable)

| Concern | Required | Forbidden |
|---|---|---|
| HTTP | `httpx` | `requests` |
| Data models | `pydantic` v2 `BaseModel` | `dataclasses` |
| Settings | `pydantic-settings` `BaseSettings` | manual env parsing |
| Logging | `loguru` | stdlib `logging` |
| Testing | `pytest` functions + fixtures | `unittest.TestCase` |
| Package manager | `uv` | bare `pip` |
| Lint + format | `ruff` | `black`, `flake8` |
| Python | 3.11+ features (`X \| Y`, `match`) | <3.11 patterns |

All public functions: type hints on every parameter and return value + Google-style docstring.

---

## Critical Constraints

1. **Never break the public API** in `__init__.py` without a CHANGELOG entry and a major version bump.
2. **Every feature needs a test** before it is considered done. No exceptions.
3. **Schema changes in cache.py** require a new migration entry in the `MIGRATIONS` list — never ALTER tables directly.
4. **Tally XML encoding**: send requests as UTF-8, decode responses as `response.content.decode('utf-16', errors='replace')`.
5. **sync.py must never raise** on Tally errors — always return `SyncResult(success=False)`.
6. **query_tally_data MCP tool** must reject any SQL containing write keywords with a clear error message.
7. **Tests must pass without a real Tally installation** — use `tests/mock_tally.py` for all HTTP tests.

---

## Tally XML Protocol (Read Before Touching connection.py or parser.py)

Tally runs an HTTP server on port 9000. You POST UTF-8 XML to it.

**Collection export request:**
```xml
<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>MyCollection</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
        <SVCURRENTCOMPANY>Company Name</SVCURRENTCOMPANY>
      </STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="MyCollection" ISMODIFY="No">
            <TYPE>Ledger</TYPE>
            <FETCH>NAME,GUID,ALTERID,PARENT</FETCH>
            <FILTER>AlterIDFilter</FILTER>
          </COLLECTION>
          <SYSTEM TYPE="Formulae" NAME="AlterIDFilter">$ALTERID > 0</SYSTEM>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>
```

**Key quirks:**
- Connection refused = Tally not running (not an HTTP 4xx/5xx — it's a socket error)
- `<LINEERROR>` tag in response = Tally error (company not loaded, invalid request)
- Amounts: `"1234.56 Dr"` or `"1234.56 Cr"` — parse the suffix for sign, not number sign
- Dates: `"YYYYMMDD"` format — `"20250415"` = April 15 2025
- Booleans: `"Yes"` / `"No"` strings
- Empty/null: `<TAG/>` or `<TAG></TAG>` = None
- AlterID incremental filter: `$ALTERID > {last_alter_id}`
- Response is UTF-16 — always decode explicitly

---

## Common Commands

```bash
uv sync --dev                          # Install all dependencies
uv run pytest tests/ -v                # Run all tests
uv run pytest tests/test_cache.py -v  # Run one test file
uv run pytest tests/ --cov=src/tallybridge --cov-report=term-missing  # Coverage
uv run ruff check src/ tests/         # Lint
uv run mypy src/                       # Type check
uv build                               # Build package
uv run tallybridge --help             # Test CLI
```

---

## Sync Algorithm

Order always: `group → ledger → voucher_type → stock_item → voucher`

For each entity:
1. `last_alter_id` ← DuckDB `sync_state` table (0 if first sync)
2. `max_alter_id` ← Tally current max
3. If equal → skip (nothing changed)
4. If `max > last` → fetch where `ALTERID > last`, parse, upsert, update sync_state
5. On any error → log warning, keep last_alter_id unchanged, return `SyncResult(success=False)`

---

## Coverage Targets

| Module | Target |
|---|---|
| `connection.py` | 95% |
| `parser.py` | 95% |
| `cache.py` | 95% |
| `sync.py` | 90% |
| `query.py` | 90% |
| `config.py` | 90% |
| `mcp/` | 85% |
| **Overall** | **90%** |

---

## External References

**TallyConnector Postman Collection** — the most complete public reference for Tally XML request formats, covering every collection type, field name, and TDL filter syntax:
`https://documenter.getpostman.com/view/13855108/TzeRpAMt`

Consult this before writing any XML in `connection.py` or any parser method in `parser.py`. It documents the exact tag names Tally uses for each field (e.g. `LEDMAILINGNAME`, `BASICDUEDATEOFPYMT`, `ISCANCELLED`) which must match precisely.

---

## When In Doubt

- Explicit over implicit
- Simpler over clever
- Raise clear errors over silent failures
- Check `tests/mock_tally.py` to understand Tally response format before writing parser code
- If a spec is ambiguous, make the conservative choice and add a `# NOTE:` comment explaining it
