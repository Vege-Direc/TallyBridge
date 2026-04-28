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
8. Run the **Pre-Commit Checklist** (see below) — all checks must pass
9. Commit with the message format: `feat(<module>): <one line description>`
10. Go back to step 1
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
4. **Tally XML encoding**: send requests and decode responses using `config.tally_encoding` (default `"utf-8"`). Previously hardcoded as UTF-16 — now configurable since Phase 8e. Tally mirrors the request encoding in its response.
5. **sync.py must never raise** on Tally errors — always return `SyncResult(success=False)`.
6. **query_tally_data MCP tool** must use a DuckDB read-only connection (`duckdb.connect(db_path, read_only=True)`) — never fall back to the read-write connection. Phase 8d removed the old keyword blocklist approach.
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
- Response encoding matches request encoding — controlled by `config.tally_encoding` (default `"utf-8"`)
- # NOTE on STATUS: Official docs say 0=failure, but TallyPrime returns 0 for empty collections.
  STATUS=-1 is an actual error. STATUS=1 is success. Log STATUS=0 at debug level.

---

## Common Commands

```bash
uv sync --extra dev                          # Install all dependencies
uv run pytest tests/ -v                      # Run all tests
uv run pytest tests/test_cache.py -v         # Run one test file
uv run pytest tests/ --cov=src/tallybridge --cov-report=term-missing  # Coverage
uv run ruff check src/ tests/                # Lint
uv run ruff format src/ tests/               # Format
uv run mypy src/                              # Type check
uv build                                      # Build package
uv run tallybridge --help                     # Test CLI
```

---

## Pre-Commit Checklist (MANDATORY before every commit)

Before committing ANY change to `src/`, run **all five** checks below.
If any fail, fix them before committing. Do not skip or defer.

```bash
# 1. Lint — zero errors required
uv run ruff check src/ tests/

# 2. Format — zero changes required
uv run ruff format --check src/ tests/

# 3. Type check — new code must be clean (pre-existing errors are OK to leave)
uv run mypy src/

# 4. Tests — all must pass
uv run pytest tests/ -q

# 5. Dependency sync — verify pyproject.toml matches actual imports
uv run python -c "
import importlib, re, subprocess
result = subprocess.run(['uv', 'pip', 'list', '--format=json'], capture_output=True, text=True)
installed = {p['name'].lower().replace('-','_') for p in __import__('json').loads(result.stdout)}
# Check that every third-party import in src/ has a corresponding dep
import_map = {'httpx':'httpx','duckdb':'duckdb','pydantic':'pydantic',
    'pydantic_settings':'pydantic-settings','mcp':'mcp','loguru':'loguru',
    'typer':'typer','dotenv':'python-dotenv','rich':'rich','tenacity':'tenacity',
    'supabase':'supabase','hashlib':None,'base64':None,'html':None,
    're':None,'os':None,'json':None,'asyncio':None,'datetime':None,
    'decimal':None,'enum':None,'contextlib':None,'dataclasses':None,
    'typing':None,'pathlib':None,'subprocess':None}
ok = True
for mod, pkg in import_map.items():
    if pkg and pkg.replace('-','_') not in installed:
        print(f'MISSING DEP: import {mod} needs {pkg} in pyproject.toml')
        ok = False
if ok: print('All imports have corresponding dependencies.')
"
```

### Dependency Rules

1. **Every third-party import in `src/` must be listed in `pyproject.toml [project.dependencies]`** (or `[project.optional-dependencies]` if conditional).
2. **Adding a new import?** → Add the package to `pyproject.toml` AND run `uv lock` / `uv sync`.
3. **Removing an import?** → Check if anything else uses it before removing from `pyproject.toml`.
4. **stdlib modules** (hashlib, base64, re, os, etc.) do NOT go in `pyproject.toml`.
5. **CI runs `uv sync --extra dev`** which installs only what's in `pyproject.toml` + `uv.lock`. If a dep is missing there, CI will fail with `ModuleNotFoundError`.

### Other Pre-Commit Checks

- **New config fields** → Add to `README.md` Configuration table AND `CHANGELOG.md`
- **New MCP tools** → Update the tool count assertion in `tests/test_mcp.py`
- **New database columns/tables** → Add a migration entry in `cache.py:MIGRATIONS` list
- **New public API functions** → Add to `src/tallybridge/__init__.py` exports
- **New CLI commands** → Verify `tallybridge --help` still renders correctly

---

## Sync Algorithm

Order always: `group → ledger → voucher_type → unit → stock_group → stock_item → cost_center → voucher`

(This matches `SYNC_ORDER` in SPECS.md §7. Masters are synced before vouchers for FK integrity.)

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

**Official TallyHelp Integration Docs** — the canonical reference for XML/JSON integration:
`https://help.tallysolutions.com/integrate-with-tallyprime/`

**Analysis Document** — `docs/official-docs-analysis.md` — exhaustive comparison of TallyBridge
against official TallyHelp docs, covering security, reliability, data integrity, performance,
MCP design, version compatibility, and a consolidated 41-item recommendation roadmap.

---

## When In Doubt

- Explicit over implicit
- Simpler over clever
- Raise clear errors over silent failures
- Check `tests/mock_tally.py` to understand Tally response format before writing parser code
- If a spec is ambiguous, make the conservative choice and add a `# NOTE:` comment explaining it

---

## v1.0 Success Metrics

Before tagging v1.0, all of these must be true:

- `uv run mypy src/` → 0 errors
- `uv run ruff check src/ tests/` → All checks passed
- `uv run pytest tests/ --cov=src/tallybridge --cov-fail-under=90 -q` → All pass, 90%+
- All Phase 10 tasks (10a–10l) checked in TASKS.md
- No `# STUCK:` comments remaining in source code

### Current status (as of Phase 10)

| Metric | Target | Current |
|--------|--------|---------|
| mypy errors | 0 | 0 |
| ruff errors | 0 | 0 |
| test coverage | ≥90% | ~93% |
| total tests | - | 440+ |
| MCP tools | - | 17 |

---

## Real Tally Validation Testing

### Setup

1. Install TallyPrime (free educational edition available from tallysolutions.com)
2. Create a test company with sample data
3. Enable HTTP server: Gateway of Tally → F12 → Advanced → Enable ODBC Server = Yes
4. Default port: 9000

### Key test scenarios

1. **Sync**: Run `tallybridge sync` and verify all entity types sync without errors
2. **Incremental sync**: Create a new ledger in Tally, re-sync, verify only new records fetched
3. **Version detection**: Verify `detect_tally_version()` returns correct TallyProduct
4. **Report parsing**: Use `fetch_report("Balance Sheet", parse=True)` and verify structured output
5. **Deletion tracking**: Delete a ledger in Tally, run `full_sync()`, verify orphan removed
6. **ERP 9 compatibility**: Test with Tally.ERP 9 to verify LEDGERENTRIES.LIST fallback works
7. **Company filtering**: Open multiple companies, verify `company` parameter filters correctly
8. **Authentication**: Test HTTP transport with and without mcp_api_key

### Version compatibility matrix

| Tally Version | ALLLEDGERENTRIES.LIST | JSON API | Base64 Encoding | TallyDrive |
|---------------|----------------------|----------|-----------------|------------|
| Tally.ERP 9   | No (fallback)        | No       | No              | No         |
| TallyPrime 1  | Yes                  | No       | No              | No         |
| TallyPrime 4  | Yes                  | No       | No              | No         |
| TallyPrime 7  | Yes                  | Yes      | Yes             | Yes        |
