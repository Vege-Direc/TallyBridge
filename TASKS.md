# TASKS.md — TallyBridge Build Checklist

> **Instructions for Claude Code:**
> Work through these tasks in order, top to bottom.
> For each task: read the referenced SPECS.md section → implement → run the verify command → fix failures → check the box → commit.
> Never skip a failing verify command. Never check a box until verify passes.
> Commit message format: `feat(<module>): <description>`
> **Phase 0 is the foundation. Do not move to Phase 1 until every Phase 0 verify passes.**

---

## Phase 0 — Foundation and Scaffold

> **Gate:** Do not start Phase 1 until all four Phase 0 tasks have passing verify commands.
> These tasks build the foundation everything else depends on.

- [x] **0a · Directory and file tree** — Create the complete directory structure from CLAUDE.md "Repository Layout" with stub content in every file. Rules: every `__init__.py` → one-line docstring `"""<Package> package."""`; every `src/tallybridge/*.py` → `"""<Purpose> — see SPECS.md §<N>."""`; every `tests/test_*.py` → `"""Tests for <module> — populated in a later task."""`. Also write real content for: `pyproject.toml` (from the provided file), `README.md` (description + quickstart), `LICENSE` (MIT, current year), `.gitignore` (Python standard — include `__pycache__`, `*.pyc`, `.env`, `*.duckdb`, `dist/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`), `CHANGELOG.md` (`## [Unreleased]` stub).
  ```
  verify:
    uv run python -c "
  import os, sys
  required = [
    'src/tallybridge/__init__.py','src/tallybridge/config.py',
    'src/tallybridge/exceptions.py','src/tallybridge/connection.py',
    'src/tallybridge/parser.py','src/tallybridge/cache.py',
    'src/tallybridge/sync.py','src/tallybridge/query.py',
    'src/tallybridge/cli.py',
    'src/tallybridge/models/__init__.py','src/tallybridge/models/master.py',
    'src/tallybridge/models/voucher.py','src/tallybridge/models/report.py',
    'src/tallybridge/mcp/__init__.py','src/tallybridge/mcp/server.py',
    'src/tallybridge/mcp/tools.py',
    'src/tallybridge/cloud/__init__.py','src/tallybridge/cloud/supabase.py',
    'tests/conftest.py','tests/mock_tally.py',
    'tests/test_exceptions.py','tests/test_config.py','tests/test_models.py',
    'tests/test_connection.py','tests/test_parser.py','tests/test_cache.py',
    'tests/test_sync.py','tests/test_query.py','tests/test_mcp.py',
    'tests/test_cli.py','tests/test_integration.py',
    'pyproject.toml','README.md','LICENSE','.gitignore','CHANGELOG.md',
  ]
  missing = [f for f in required if not os.path.exists(f)]
  if missing: print('MISSING:', missing); sys.exit(1)
  print('All', len(required), 'required files present')
  "
  commit: chore: scaffold complete directory and file tree with stubs
  ```

- [x] **0b · Dependencies and importability** — Run `uv sync --dev` and confirm every package in the `src/tallybridge` tree is importable. If any import fails, the stub file is missing its `__init__.py` or has a syntax error — fix it before continuing.
  ```
  verify:
    uv sync --dev
    uv run python -c "import tallybridge; print('tallybridge OK')"
    uv run python -c "import tallybridge.config; print('config OK')"
    uv run python -c "import tallybridge.exceptions; print('exceptions OK')"
    uv run python -c "import tallybridge.models.master; print('models.master OK')"
    uv run python -c "import tallybridge.models.voucher; print('models.voucher OK')"
    uv run python -c "import tallybridge.models.report; print('models.report OK')"
    uv run python -c "import tallybridge.mcp.tools; print('mcp.tools OK')"
    uv run python -c "import tallybridge.cloud.supabase; print('cloud.supabase OK')"
  commit: chore: confirm all packages importable with stub content
  ```

- [x] **0c · Tooling baseline** — Verify ruff, mypy, and pytest all run against the stubs without crashing. Stubs have no real code so there should be zero lint issues and zero type errors. Fix any tool configuration problems discovered here — it is far easier to fix them now than after real code exists.
  ```
  verify:
    uv run ruff check src/ tests/
    # Must print: "All checks passed." — fix pyproject.toml [tool.ruff] if not

    uv run mypy src/
    # Must print: "Success: no issues found" — fix mypy config if not

    uv run pytest tests/ --collect-only -q
    # Must exit 0 — "no tests ran" is correct at this stage
    # ImportError during collection = broken stub, fix it

    uv run pytest tests/ -v
    # Must exit 0 — zero tests collected is a pass here
  commit: chore: confirm ruff, mypy, and pytest all run clean on stubs
  ```

- [x] **0d · CI workflows** — Write `.github/workflows/test.yml` (trigger: push + PR; matrix: `ubuntu-latest`, `windows-latest`, `macos-latest`; steps: checkout → setup-uv with python 3.11 → `uv sync --dev` → `uv run ruff check src/` → `uv run pytest tests/ -v`). Write `.github/workflows/publish.yml` (trigger: `v*` tags; environment: `pypi`; uses PyPI Trusted Publishing via `pypa/gh-action-pypi-publish`; steps: `uv build` → publish).
  ```
  verify:
    uv run python -c "
  import yaml, sys
  with open('.github/workflows/test.yml') as f:
      doc = yaml.safe_load(f)
  matrix = doc['jobs']['test']['strategy']['matrix']['os']
  for expected in ['ubuntu-latest', 'windows-latest', 'macos-latest']:
      assert expected in matrix, f'Missing from matrix: {expected}'
  print('CI matrix OK:', matrix)
  "
  # If yaml not available: uv add pyyaml --dev
  commit: ci: add test matrix and PyPI trusted publishing workflows
  ```

---

## Phase 1 — Foundation

- [x] **exceptions.py** — Implement `src/tallybridge/exceptions.py`. Spec: SPECS.md §1. Write `tests/test_exceptions.py`.
  ```
  verify: uv run pytest tests/test_exceptions.py -v
  commit: feat(exceptions): add custom exception hierarchy
  ```

- [x] **config.py** — Implement `src/tallybridge/config.py` with `TallyBridgeConfig` and `get_config()`. Spec: SPECS.md §2. Write `tests/test_config.py`.
  ```
  verify: uv run pytest tests/test_config.py -v --cov=src/tallybridge/config --cov-fail-under=90
  commit: feat(config): add pydantic-settings config with singleton
  ```

---

## Phase 2 — Data Models

- [x] **models/master.py** — Implement `TallyLedger`, `TallyGroup`, `TallyStockItem`, `TallyGodown`, `TallyVoucherType`, `TallyUnit`, `TallyStockGroup`, `TallyCostCenter`. Spec: SPECS.md §3a.
  ```
  verify: uv run pytest tests/test_models.py::test_master -v
  commit: feat(models): add master data models
  ```

- [x] **models/voucher.py** — Implement `TallyVoucher`, `TallyVoucherEntry`, `TallyInventoryEntry`. Spec: SPECS.md §3b.
  ```
  verify: uv run pytest tests/test_models.py::test_voucher -v
  commit: feat(models): add voucher models
  ```

- [x] **models/report.py** — Implement `DailyDigest`, `OutstandingBill`, `TrialBalanceLine`, `StockAgingLine`, `SyncResult`. Update `models/__init__.py` to re-export all. Spec: SPECS.md §3c. Write all model tests in `tests/test_models.py`.
  ```
  verify: uv run pytest tests/test_models.py -v
  commit: feat(models): add report models and complete __init__ exports
  ```

---

## Phase 3 — Core Stack (implement in this order — each depends on the previous)

- [x] **mock_tally.py** — Write `tests/mock_tally.py`: a `pytest-httpserver`-based mock Tally server returning realistic XML for all entity types. Spec: SPECS.md §11a. This is not production code — it's a test helper, but it must be correct.
  ```
  verify: uv run python -c "
  from tests.mock_tally import (
      SAMPLE_LEDGERS, SAMPLE_GROUPS, SAMPLE_VOUCHERS,
      SAMPLE_UNITS, SAMPLE_STOCK_GROUPS, SAMPLE_STOCK_ITEMS, SAMPLE_COST_CENTERS,
  )
  print(len(SAMPLE_LEDGERS), 'ledgers')
  print(len(SAMPLE_GROUPS), 'groups')
  print(len(SAMPLE_UNITS), 'units')
  print(len(SAMPLE_STOCK_GROUPS), 'stock groups')
  print(len(SAMPLE_STOCK_ITEMS), 'stock items')
  print(len(SAMPLE_COST_CENTERS), 'cost centers')
  print(len(SAMPLE_VOUCHERS), 'vouchers')
  assert len(SAMPLE_LEDGERS) >= 10, 'Need at least 10 ledgers'
  assert len(SAMPLE_VOUCHERS) >= 7, 'Need at least 7 vouchers incl cancelled'
  print('mock_tally sample data OK')
  "
  commit: test: add mock Tally HTTP server with sample data
  ```

- [x] **connection.py** — Implement `src/tallybridge/connection.py`. Spec: SPECS.md §4. Write `tests/test_connection.py` using mock_tally.
  ```
  verify: uv run pytest tests/test_connection.py -v --cov=src/tallybridge/connection --cov-fail-under=90
  commit: feat(connection): add TallyConnection with retry and error handling
  ```

- [x] **parser.py** — Implement `src/tallybridge/parser.py`. Spec: SPECS.md §5. Write `tests/test_parser.py` using XML strings from mock_tally.
  ```
  verify: uv run pytest tests/test_parser.py -v --cov=src/tallybridge/parser --cov-fail-under=95
  commit: feat(parser): add XML parser with amount/date/bool helpers
  ```

- [x] **cache.py** — Implement `src/tallybridge/cache.py` with full DuckDB schema, all upsert methods, and migration system. Spec: SPECS.md §6. Write `tests/test_cache.py`.
  ```
  verify: uv run pytest tests/test_cache.py -v --cov=src/tallybridge/cache --cov-fail-under=95
  commit: feat(cache): add DuckDB cache with schema, upserts, and migrations
  ```

- [x] **sync.py** — Implement `src/tallybridge/sync.py`. Spec: SPECS.md §7. Write `tests/test_sync.py` using `AsyncMock`.
  ```
  verify: uv run pytest tests/test_sync.py -v --cov=src/tallybridge/sync --cov-fail-under=90
  commit: feat(sync): add AlterID-based incremental sync engine
  ```

---

## Phase 4 — API and Interfaces

- [x] **conftest.py** — Write `tests/conftest.py` with all shared fixtures: `mock_tally_server`, `tmp_db`, `populated_db`, `tally_query`, `tally_connection`. Spec: SPECS.md §11b. The `populated_db` fixture must load realistic sample data so all query tests work.
  ```
  verify: uv run pytest tests/ --collect-only 2>&1 | grep "test session starts"
  commit: test: add shared fixtures and populated test database
  ```

- [x] **query.py** — Implement `src/tallybridge/query.py`. Spec: SPECS.md §8. Write `tests/test_query.py` using the `tally_query` fixture from conftest.
  ```
  verify: uv run pytest tests/test_query.py -v --cov=src/tallybridge/query --cov-fail-under=90
  commit: feat(query): add TallyQuery public API
  ```

- [x] **mcp/tools.py + mcp/server.py** — Implement MCP server and all 12 tools. Spec: SPECS.md §9. Write `tests/test_mcp.py`.
  ```
  verify: uv run pytest tests/test_mcp.py -v --cov=src/tallybridge/mcp --cov-fail-under=85
  commit: feat(mcp): add MCP server with 12 tools
  ```

- [x] **cli.py** — Implement `src/tallybridge/cli.py` with all commands including `init` wizard. Spec: SPECS.md §10. Write `tests/test_cli.py`.
  ```
  verify: uv run pytest tests/test_cli.py -v && uv run tallybridge --help
  commit: feat(cli): add Typer CLI with init wizard and all commands
  ```

---

## Phase 5 — Integration and Public API

- [x] **__init__.py** — Implement the stable public API contract. Spec: SPECS.md §12. Include the `connect()` convenience function.
  ```
  verify: uv run python -c "import tallybridge; print(tallybridge.__version__)"
  commit: feat: expose stable public API in __init__.py
  ```

- [x] **Integration tests** — Write `tests/test_integration.py`: full end-to-end flow using mock_tally → sync_all → query. Spec: SPECS.md §11c.
  ```
  verify: uv run pytest tests/test_integration.py -v
  commit: test: add end-to-end integration tests
  ```

---

## Phase 6 — Recipes and Docs

- [x] **recipes/** — Write all four recipe scripts. Spec: SPECS.md §13. Each must run standalone and fail gracefully when Tally is not connected.
  ```
  verify: uv run python recipes/daily_digest.py 2>&1 | grep -E "(sales|Could not connect)"
  commit: feat(recipes): add daily digest, receivables, GST, and anomaly detector
  ```

- [x] **docs/** — Write `docs/tally-setup.md` (how to enable Tally HTTP server) and `docs/mcp-setup.md` (claude_desktop_config.json setup). Update `README.md` with `connect()` quickstart.
  ```
  verify: cat docs/tally-setup.md | grep "9000"   # confirm port mentioned
  commit: docs: add Tally setup guide and MCP connection guide
  ```

---

## Phase 7 — Polish and Release Prep

- [x] **Linting** — Run `uv run ruff check src/ tests/` and fix every reported issue. Run `uv run ruff format src/ tests/`.
  ```
  verify: uv run ruff check src/ tests/   # must output: All checks passed.
  commit: style: fix all ruff lint and format issues
  ```

- [x] **Type checking** — Run `uv run mypy src/` and fix all type errors. Add `# type: ignore[<code>]` only for genuine third-party stub gaps, with a comment explaining why.
  ```
  verify: uv run mypy src/   # must output: Success: no issues found
  commit: fix(types): resolve all mypy type errors
  ```

- [x] **Full test suite + coverage** — Run all tests with coverage. Fix any gaps below target.
  ```
  verify: uv run pytest tests/ --cov=src/tallybridge --cov-fail-under=90 -v
  commit: test: achieve 90%+ overall coverage
  ```

- [x] **Build verification** — Build the package and verify the wheel installs cleanly.
  ```
  verify: uv build && uv pip install dist/tallybridge-0.1.0-*.whl --dry-run
  commit: chore: confirm package builds and installs correctly
  ```

- [x] **CHANGELOG + version** — Write `CHANGELOG.md` entry for v0.1.0. Confirm `pyproject.toml` version is `0.1.0`. Confirm all GitHub URLs reference the real repo.
  ```
  verify: grep "0.1.0" CHANGELOG.md pyproject.toml src/tallybridge/__init__.py
  commit: chore: finalise v0.1.0 release metadata
  ```

---

## Phase 8 — Recommendations v2 Implementation

> **Gate:** P0 items must be completed before P1 items. Each task references RECOMMENDATIONS.md v2.
> Order: quick P0 fixes first, then P1 core features, then MCP rewrite.

- [x] **8a · P0-6: DECIMAL precision loss** — Remove all `float()` conversions in `cache.py`.
  The following lines convert `Decimal` to `float` before DuckDB insertion, silently losing
  precision for financial amounts: lines 207, 253-258, 365-366, 374, 384-386. DuckDB's Python
  driver accepts `Decimal` objects natively — pass them directly.
  ```
  verify: uv run pytest tests/test_cache.py tests/test_query.py tests/test_mcp.py -v
  commit: fix(cache): remove float() conversions to preserve DECIMAL precision
  ```

- [x] **8b · P0-2: XML entity escaping** — Add `html.escape()` to `connection.py` for all
  user-supplied strings injected into XML payloads. Specifically escape `company` name in
  `_build_collection_xml()` (line 164) and `filter_expr` (line 170). Also escape
  `collection_name` and `tally_type` for safety.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: fix(connection): add XML entity escaping to prevent injection
  ```

- [x] **8c · P0-3: Tally response error checking** — Add `<EXCEPTION>` prefix check and
  `<STATUS>` tag check to `connection.py:post_xml()`. Check EXCEPTION first (per
  tally-mcp-server reference), then STATUS (per TallyHelp docs): `1`=success, `0`=no data,
  `-1`=error. Currently only `<LINEERROR>` is checked.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: fix(connection): add EXCEPTION and STATUS response checking
  ```

- [x] **8d · P0-4: SQL injection prevention** — Replace the bypassable `is_safe_sql()` in
  `server.py` with a DuckDB read-only connection for `query_tally_data`. Add a
  `_read_conn` property to `TallyCache` that opens `duckdb.connect(db_path, read_only=True)`.
  Remove the `FORBIDDEN_SQL` set and `is_safe_sql()` function entirely.
  ```
  verify: uv run pytest tests/test_mcp.py tests/test_cache.py -v
  commit: fix(mcp): use DuckDB read-only connection for SQL queries
  ```

- [x] **8e · P0-5: Encoding alignment** — Fix `connection.py:post_xml()` to decode the
  response using the same encoding as the request. Currently sends UTF-8 but decodes UTF-16.
  Add `tally_encoding` config field (default `"utf-8"`). When `utf-8`: encode body as UTF-8,
  decode response as UTF-8. When `utf-16`: encode as UTF-16LE, decode as UTF-16LE.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: fix(connection): align request/response encoding
  ```

- [x] **8f · P2-3: httpx connection pooling** — Replace `tenacity` retry with httpx
  transport-level retries in `connection.py`. Use `httpx.AsyncHTTPTransport(retries=3)`,
  configure `Limits` and `Timeout`. Keep tenacity only if exponential backoff on
  application-level errors is needed.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: perf(connection): use httpx transport retries instead of tenacity
  ```

- [x] **8g · P1-1: Voucher pagination** — Implement batched voucher fetching in `sync.py`
  using AlterID ranges. Update `VOUCHER_BATCH_SIZE` from 1000 to 5000. Loop: fetch batch
  via `$ALTERID > last_id AND $ALTERID <= last_id + batch_size`, parse, upsert, advance
  last_id, repeat until empty batch.
  ```
  verify: uv run pytest tests/test_sync.py -v
  commit: feat(sync): implement batched voucher fetching with batch size 5000
  ```

- [x] **8h · P1-2: Company selection** — Pass `tally_company` from config through to
  `TallyConnection.export_collection()` and `get_alter_id_max()` calls in `sync.py`. Add
  `company` column to all DuckDB tables via migration. Filter queries by active company.
  Auto-detect company from Tally on first sync if `tally_company` is blank.
  ```
  verify: uv run pytest tests/test_sync.py tests/test_cache.py tests/test_query.py -v
  commit: feat(sync): add company selection and multi-company tracking
  ```

- [x] **8i · P1-3+5: Cost centre and bill allocation tables** — Add `trn_cost_centre` and
  `trn_bill` tables to cache.py schema (already defined in SPECS.md §6 but not implemented).
  Add parser support for `<COSTCENTRE.LIST>` and `<BILLALLOCATIONS.LIST>` in vouchers. Add
  upsert methods and update `upsert_vouchers()` to populate these tables.
  ```
  verify: uv run pytest tests/test_cache.py tests/test_parser.py -v
  commit: feat(cache): implement trn_cost_centre and trn_bill tables
  ```

- [x] **8j · P0-1: MCP server rewrite** — Rewrite `mcp/server.py` and `mcp/tools.py` using
  the official `mcp` Python SDK's `FastMCP` class. Implement lifespan pattern for resource
  management, `@mcp.tool()` decorators, tool annotations (`readOnlyHint=True`,
  `openWorldHint=False`), and `CallToolResult(is_error=True)` error handling. Support both
  `stdio` and `streamable-http` transports. Keep the old `TallyMCPServer` class as a
  fallback until the rewrite is verified.
  ```
  verify: uv run pytest tests/test_mcp.py -v
  commit: feat(mcp): rewrite server using official MCP Python SDK
  ```

---

## Phase 9 — Analysis-Driven Improvements

> **Source:** docs/official-docs-analysis.md — consolidated recommendations C1–C41.
> **Gate:** P0 items (9a–9h) must be completed before P1 items (9i–9t). Each task references the analysis doc.
> Order: correctness & security first, then data integrity & performance, then features.

### Phase 9A — P0: Correctness & Security

- [x] **9a · C7: Catch ReadTimeout in post_xml()** — Add `httpx.ReadTimeout` to the except
  clause in `connection.py:post_xml()`. Currently only `ConnectError` and `ConnectTimeout`
  are caught. ReadTimeout during a large voucher batch fetch propagates as a generic
  `Exception`, losing error classification. Raise `TallyConnectionError` with a
  descriptive message (include the timeout value and suggest reducing batch size).
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: fix(connection): catch ReadTimeout and raise TallyConnectionError
  ```

- [x] **9b · C9: Fix parse_date safety — no date.today() fallback** — In `parser.py`,
  `parse_vouchers()` uses `date=self.parse_date(...) or date.today()` which silently
  substitutes today's date for corrupt/missing dates, corrupting financial reports.
  Change to: if `parse_date()` returns `None`, skip the record with a warning log
  (or set `date=None` and let the caller decide). Also fix the same pattern in
  `cache.py:_get_outstanding()`.
  ```
  verify: uv run pytest tests/test_parser.py tests/test_cache.py tests/test_query.py -v
  commit: fix(parser): never silently fall back to date.today() for unparseable dates
  ```

- [x] **9c · C1: Document STATUS semantics + debug logging** — Add `logger.debug()`
  for STATUS=0 responses in `connection.py:post_xml()`. Add a code comment block
  explaining the STATUS value discrepancy between official docs and observed behavior
  (official says 0=failure, TallyPrime returns 0 for empty collections). Add a
  `strict_status: bool = False` config field — when True, treat STATUS=0 as error.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add STATUS semantics documentation and debug logging
  ```

- [x] **9d · C2: Always include SVCURRENTCOMPANY after first sync** — After
  auto-detecting the company on first sync (implemented in 8h), store it in the
  sync engine and ALWAYS include it in subsequent requests. Add a warning log
  when operating without a company. `get_company_list()` and `ping()` may omit it.
  ```
  verify: uv run pytest tests/test_sync.py tests/test_connection.py -v
  commit: fix(sync): always include SVCURRENTCOMPANY after first company detection
  ```

- [x] **9e · C10: Fix query_readonly() — use truly read-only DuckDB connection** —
  The current `query_readonly()` in `cache.py` can fall back to the read-write
  connection when `BEGIN READ ONLY` fails. Replace with a separate
  `duckdb.connect(db_path, read_only=True)` connection. Remove the fallback path
  entirely. The read-only connection physically prevents all write operations.
  ```
  verify: uv run pytest tests/test_cache.py tests/test_mcp.py -v
  commit: fix(cache): use separate read-only DuckDB connection for queries
  ```

- [x] **9f · C8: Fix sync_state advancement past failed upserts** — In `sync.py`,
  `update_sync_state()` is called with `max_alter_id` from Tally, which can be
  higher than the last successfully upserted record. Track the highest alter_id
  that was actually committed to DuckDB and only advance sync_state to that value.
  Failed records will then be retried on the next sync cycle.
  ```
  verify: uv run pytest tests/test_sync.py -v
  commit: fix(sync): only advance sync_state to last successfully committed alter_id
  ```

- [x] **9g · C6: Add application-level retry with exponential backoff** —
  Transport-level retries (httpx `retries=3`) only cover TCP errors. Add
  `tenacity` retry with exponential backoff on `httpx.ReadTimeout` and
  transient `TallyDataError` in `connection.py:post_xml()`. Max 3 retries,
  starting at 1s, max 10s wait. Log each retry at warning level.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add application-level retry with exponential backoff
  ```

- [x] **9h · C11: Add authentication layer for MCP HTTP transport** — Add an
  `mcp_api_key: str | None = None` config field. When running in HTTP transport
  mode, validate `Authorization: Bearer <key>` header on every request. Reject
  unauthenticated requests with 401. For stdio transport, auth is not needed
  (local process trust). Document the setup in `docs/mcp-setup.md`.
  ```
  verify: uv run pytest tests/test_mcp.py -v
  commit: feat(mcp): add API key authentication for HTTP transport
  ```

### Phase 9B — P1: Data Integrity & Performance

- [x] **9i · C19: Add record count reconciliation after sync** — After each sync
  cycle, compare `COUNT(*)` in the cache table against the count returned by Tally
  for each entity type. Log a warning on discrepancy. Add a `reconcile=True`
  parameter to `sync_all()`.
  ```
  verify: uv run pytest tests/test_sync.py -v
  commit: feat(sync): add record count reconciliation after sync cycle
  ```

- [x] **9j · C18: Add content hashes for drift detection** — Add a `content_hash`
  column to each master table (`mst_ledger`, `mst_group`, `mst_stock_item`, etc.)
  computed from key fields. On `full_sync()`, compare hashes and log mismatches.
  Use a migration to add the column.
  ```
  verify: uv run pytest tests/test_cache.py -v
  commit: feat(cache): add content_hash column for drift detection
  ```

- [x] **9k · C20: Add FK reconciliation for ledger entries** — Add a
  `reconcile_orphans()` method to `TallyCache` that detects ledger entries in
  `trn_ledger_entry` referencing ledgers not in `mst_ledger`. Return the orphan
  count and log a warning. Call this from `health_check()`.
  ```
  verify: uv run pytest tests/test_cache.py -v
  commit: feat(cache): add FK reconciliation for orphaned ledger entries
  ```

- [x] **9l · C21: Use batch SQL (executemany) for upserts** — Replace row-by-row
  `conn.execute()` loops in all `upsert_*()` methods with `conn.executemany()`.
  For `upsert_vouchers()` with child tables, collect all child rows and use
  executemany for each child table. This is 10-100x faster for large batches.
  ```
  verify: uv run pytest tests/test_cache.py -v
  commit: perf(cache): use executemany for batch upserts
  ```

- [x] **9m · C22: Add pagination for non-voucher master entities** — Apply the same
  AlterID-range batching used for vouchers to all entity types when the record count
  exceeds a threshold (e.g., 5000). Currently only vouchers use batched fetching.
  ```
  verify: uv run pytest tests/test_sync.py -v
  commit: feat(sync): add AlterID-range pagination for master entities
  ```

- [x] **9n · C35: Make VOUCHER_BATCH_SIZE configurable** — Move `VOUCHER_BATCH_SIZE`
  from a hardcoded constant to `TallyBridgeConfig` with default 5000 and max 10000.
  Pass it through to `TallySyncEngine`.
  ```
  verify: uv run pytest tests/test_sync.py tests/test_config.py -v
  commit: feat(config): make VOUCHER_BATCH_SIZE configurable
  ```

- [x] **9o · C34: Optimize health_check() — single query** — Replace the 10 separate
  `SELECT COUNT(*) FROM <table>` queries with a single `UNION ALL` query.
  ```
  verify: uv run pytest tests/test_cache.py -v
  commit: perf(cache): consolidate health_check COUNT queries into single UNION ALL
  ```

### Phase 9C — P1: Feature Completeness

- [x] **9p · C3: Add base64 encoding for multilingual entity names** — Add support
  for the `id-encoded` header used with TallyPrime 7.0 JSON integration for
  non-ASCII entity names. Also needed for Object-level export with Unicode names.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add base64 encoding support for multilingual entity names
  ```

- [x] **9q · C12: Add export_object() for single-record lookups** — Add an
  `export_object()` method to `TallyConnection` using the official TYPE=Object
  XML pattern. Supports lookup by Name or GUID. Useful for targeted queries
  without a full collection fetch.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add export_object for single-record lookups
  ```

- [x] **9r · C13: Add fetch_report() for Balance Sheet, P&L, Trial Balance** — Add
  a `fetch_report()` method to `TallyConnection` using the official TYPE=Data
  XML pattern. Support report IDs: "Balance Sheet", "Profit & Loss", "Day Book",
  "Trial Balance". Parse the response and return structured data.
  ```
  verify: uv run pytest tests/test_connection.py tests/test_parser.py -v
  commit: feat(connection): add fetch_report for Tally computed reports
  ```

- [x] **9s · C17: Add version-aware feature gating** — Extend `version.py` to
  provide a `capabilities()` method that returns which features are available for
  the detected Tally version. Use this in `TallyConnection` and `TallySyncEngine`
  to auto-disable unavailable features and guide users to upgrade.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add version-aware feature gating
  ```

- [x] **9t · C16: Enhance search() with fuzzy matching** — Add trigram-based fuzzy
  search to `query.py:search()` using DuckDB's string similarity functions. Fall
  back to ILIKE when trigram extension is unavailable.
  ```
  verify: uv run pytest tests/test_query.py -v
  commit: feat(query): add fuzzy matching to search using trigram similarity
  ```

### Phase 9D — P2: Developer Experience & Reliability

- [x] **9u · C32: Add circuit breaker for run_continuous()** — Implement exponential
  backoff in `sync.py:run_continuous()` when Tally is unreachable. Start at
  `frequency_minutes`, double on each failure up to 60 minutes, reset on success.
  ```
  verify: uv run pytest tests/test_sync.py -v
  commit: feat(sync): add circuit breaker with exponential backoff to run_continuous
  ```

- [x] **9v · C33: Add graceful shutdown for run_continuous()** — Add an
  `asyncio.Event` for shutdown signal. Break out of `asyncio.sleep()` on signal.
  Register signal handlers for SIGINT/SIGTERM.
  ```
  verify: uv run pytest tests/test_sync.py -v
  commit: feat(sync): add graceful shutdown to run_continuous
  ```

- [x] **9w · C24+C25: Document API Explorer and sample files** — Add links to
  TallyPrime API Explorer and `Integration_Demo_Samples.zip` in `docs/tally-setup.md`.
  ```
  verify: grep -c "API Explorer" docs/tally-setup.md
  commit: docs: add TallyPrime API Explorer and sample files references
  ```

- [x] **9x · C26+C27: Add feature compatibility matrix** — Add a compatibility
  matrix to `docs/tally-setup.md` showing which TallyBridge features work with
  which Tally versions (ERP 9, TallyPrime 1.x-6.x, TallyPrime 7.0+).
  ```
  verify: grep -c "Tally.ERP 9" docs/tally-setup.md
  commit: docs: add feature compatibility matrix by Tally version
  ```

- [x] **9y · C23: Add TLS/HTTPS tunnel documentation** — Document SSH tunnel
  setup for secure remote Tally access in `docs/tally-setup.md`. Add a warning
  about plaintext data when `tally_host` is not localhost.
  ```
  verify: grep -c "SSH tunnel" docs/tally-setup.md
  commit: docs: add SSH tunnel setup guide for secure remote access
  ```

- [x] **9z · C41: Add error tracking table for failed records** — Add a
  `sync_errors` table to track failed record GUIDs, entity types, error messages,
  and timestamps. Add a `get_sync_errors()` method to `TallyCache`. Expose via
  MCP tool `get_sync_errors`.
  ```
  verify: uv run pytest tests/test_cache.py tests/test_mcp.py -v
  commit: feat(cache): add sync_errors table for tracking failed records
  ```

### Phase 9E — P3: TallyPrime 7.0 & Future

- [x] **9aa · C4: Add JSON request/response support** — Completed via Phase 11A
  (11a–11d). `TallyConnection` extended with `post_json()`, JSON builders, auto-format
  selection, and `id-encoded` header. Version gating via `_require_capability()`.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add JSON request/response support for TallyPrime 7.0
  ```

- [x] **9ab · C28: Support JSONEx format** — Completed via Phase 11A (11b).
  `TallyJSONParser` handles JSONEx response structure. `tally_export_format`
  config supports `"auto"` (uses JSONEx on 7.0+), `"xml"`, `"json"`.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add JSONEx format support
  ```

- [x] **9ac · C5: Handle currency symbol entity codes** — Verify ElementTree
   correctly decodes AED (`&#8387`) and SAR (`&#8385`) entity codes in XML
   responses. For the future import path, add entity code replacement logic.
  ```
  verify: uv run pytest tests/test_parser.py -v
  commit: fix(parser): verify currency symbol entity code handling
  ```

- [x] **9ad · C14: Add Import (write) capability** — Implement data import using
   `TALLYREQUEST=Import` with both XML and JSON formats. Support master and voucher
   import. Add `import_ledger()`, `import_voucher()` methods. Depends on C4 (JSON).
  ```
  verify: uv run pytest tests/test_connection.py tests/test_cache.py -v
  commit: feat(connection): add Import capability for masters and vouchers
  ```

- [x] **9ae · C15: Add fetch_gstr3b() using Tally's JSON export** — Add a method
  to fetch GSTR-3B data using TallyPrime 7.0's structured JSON export. More
  accurate than SQL reconstruction from raw voucher data.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add fetch_gstr3b using Tally 7.0 JSON export
  ```

- [x] **9af · C40: Parallel entity syncing** — Sync master entities (group, ledger,
  etc.) concurrently using `asyncio.gather()`. Sync vouchers after all masters
  complete. Keep the SYNC_ORDER constraint for voucher dependency on masters.
  ```
  verify: uv run pytest tests/test_sync.py -v
  commit: perf(sync): add parallel master entity syncing
  ```

- [x] **9ag · C31: Detect and report TSS expiry status** — Add TSS status detection
  to the `tallybridge doctor` command. Warn users with expired TSS about feature
  limitations; confirm local sync still works. Depends on C17 (version detection).
  ```
  verify: uv run pytest tests/test_cli.py -v
  commit: feat(cli): add TSS expiry status detection to doctor command
  ```

- [x] **9ah · C29: Add detailed-response header support for imports** — When using
  JSON import (TallyPrime 7.0+), include the `detailed-response` HTTP header to
  receive detailed object creation/alteration counts in the response. This provides
  accurate feedback on how many records were created, altered, or failed during
  import operations. Depends on C4 (JSON, task 9aa).
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add detailed-response header for JSON imports
  ```

- [x] **9ai · C30: Support SVExportInPlainFormat for JSON report exports** — Add
  support for the `SVExportInPlainFormat` static variable in JSON/JSONEx report
  requests. When set to `Yes`, Tally returns cleaner JSON output without TDL
  metadata wrappers, making the response easier to parse and consume. Depends on
  C4 (JSON, task 9aa).
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add SVExportInPlainFormat support for JSON reports
  ```

- [x] **9aj · C39: Add TSS renewal prompt in CLI** — When JSON or TallyPrime 7.0+
   features are unavailable due to an outdated Tally version (detected via C31/C17),
   suggest TSS renewal in the CLI output. Display a message like "TSS subscription
   expired — renew at tallysolutions.com to access TallyPrime 7.0 features (JSON,
   SmartFind, GSTR-3B export)." Depends on C31 (task 9ag).

### Phase 9F — P3: Research & Future

> **Note:** These items require further research or depend on TallyPrime 7.0+
> adoption. They are tracked here for visibility but may be deferred to v1.1+.

- [ ] **9ak · C36: Add webhook receiver for Tally push notifications** —
  Implement an HTTP endpoint that TallyPrime 7.0 can push data to using the
  new HTTP Request TDL action. This would enable event-driven sync instead
  of polling. High effort — requires a persistent HTTP server, authentication,
  and payload handling. Depends on C14 (Import, task 9ad).
  ```
  verify: uv run pytest tests/test_sync.py -v
  commit: feat(sync): add webhook receiver for Tally push notifications
  ```

- [ ] **9al · C37: Explore TallyDrive API for cloud-based sync** — Research
  whether TallyDrive's cloud backup API can be used to sync data without
  TallyPrime running locally. If feasible, implement a `TallyDriveSource`
  as an alternative to `TallyConnection`. Research item — no verify command
  until feasibility is confirmed.

- [ ] **9am · C38: Support Data Source: JSON String pattern** — TallyPrime 7.0
  allows JSON strings as TDL collection data sources. Research whether this
  enables new integration patterns (e.g., sending pre-built JSON payloads to
  Tally for processing). Research item — depends on C4 (JSON, task 9aa).

---

## Phase 10 — Production Readiness (v1.0)

> **Source:** Gap analysis from comprehensive review of code, tests, docs, and competitor research.
> **Gate:** Phase 10A (mypy + coverage) must be completed before Phase 10B (features).
> **Goal:** All mypy errors fixed, coverage ≥90%, all critical features complete, docs updated.

### Phase 10A — Fix Existing Issues (Critical Blockers)

- [x] **10a · Fix 76 mypy errors** — Fix all type errors in `sdk_server.py`, `cache.py`,
  `version.py`. Primary issues:
  - `sdk_server.py`: Use `ToolAnnotations` from `mcp.types` instead of `dict[str, bool]`
    for tool annotations; fix `isError` (not `is_error`) for `CallToolResult`; add proper
    `Context` type parameters; add return type annotations; fix `Any` returns.
  - `cache.py:534`: `TallyVoucherEntry` vs `TallyInventoryEntry` type confusion in
    `upsert_vouchers()` inventory entry loop.
  - `version.py:213,245`: Fix `Any` return from `detect_tally_version()` and missing
    `_detected_version` attribute on `TallyConnection`.
  ```
  verify: uv run mypy src/   # must output: Success: no issues found
  commit: fix(types): resolve all 76 mypy errors across sdk_server, cache, version
  ```

- [x] **10b · Add LEDGERENTRIES.LIST fallback for ERP 9** — The parser currently only
  checks `ALLLEDGERENTRIES.LIST` (TallyPrime). Tally.ERP 9 only has `LEDGERENTRIES.LIST`.
  Add fallback: if `ALLLEDGERENTRIES.LIST` returns nothing, try `LEDGERENTRIES.LIST`.
  Same for `ALLINVENTORYENTRIES.LIST` → `INVENTORYENTRIES.LIST`. This ensures complete
  data capture on both Tally.ERP 9 and TallyPrime.
  ```
  verify: uv run pytest tests/test_parser.py -v
  commit: fix(parser): add LEDGERENTRIES.LIST fallback for Tally.ERP 9 compatibility
  ```

- [x] **10c · Improve test coverage to 90%+** — Current overall coverage is 85%.
  Biggest gaps: `sdk_server.py` at 52%, `sync.py` at 79%, `parser.py` at 83%,
  `version.py` at 83%, `query.py` at 86%. Add tests for:
  - `sdk_server.py`: Auth check, lifespan setup, tool error handling, each tool's
    success and error paths.
  - `sync.py`: Circuit breaker reset, graceful shutdown signal, reconcile path,
    drift detection.
  - `parser.py`: ERP 9 LEDGERENTRIES.LIST fallback, ALLINVENTORYENTRIES.LIST,
    ACCOUNTINGALLOCATIONS.LIST, BATCHALLOCATIONS.LIST.
  - `version.py`: `capabilities()` for each product, `detect_tally_version()` paths.
  ```
  verify: uv run pytest tests/ --cov=src/tallybridge --cov-fail-under=90 -q
  commit: test: achieve 90%+ overall coverage
  ```

### Phase 10B — Feature Completeness for v1.0

- [x] **10d · Parse fetch_report() responses** — `fetch_report()` currently returns raw
  XML string with no parsing. Add parsers for:
  - Balance Sheet: Parse `<BSNAME>`, `<BSCLOSAMT>` groups into structured dict
  - Profit & Loss: Parse `<PLNAME>`, `<PLCLOSAMT>` groups into structured dict
  - Trial Balance: Parse into `list[TrialBalanceLine]`
  - Day Book: Parse into voucher list
  Return a `TallyReport` dataclass with report_type, period, and structured data.
  ```
  verify: uv run pytest tests/test_parser.py tests/test_connection.py -v
  commit: feat(parser): add report response parsers for Balance Sheet, P&L, Trial Balance
  ```

- [x] **10e · Parse export_object() responses** — `export_object()` currently returns raw
  XML. Add parser integration: detect the object type from the response, parse it
  using existing `parse_ledgers()`, `parse_vouchers()`, etc., and return the typed model.
  ```
  verify: uv run pytest tests/test_connection.py tests/test_parser.py -v
  commit: feat(connection): integrate parser with export_object for typed responses
  ```

- [x] **10f · Add 4 missing MCP tools** — Add these tools from the tally-mcp-server
  reference (RECOMMENDATIONS.md P1-6):
  - `get_balance_sheet(to_date, company?)` → grouped by asset/liability
  - `get_profit_loss(from_date, to_date, company?)` → grouped by income/expense
  - `get_ledger_account(ledger_name, from_date, to_date)` → voucher-level GL
  - `get_stock_item_account(item_name, from_date, to_date)` → quantity movements
  Update tool count assertion in `tests/test_mcp.py` (13 → 17).
  ```
  verify: uv run pytest tests/test_mcp.py tests/test_query.py -v
  commit: feat(mcp): add balance-sheet, profit-loss, ledger-account, stock-item-account tools
  ```

- [x] **10g · Add deletion tracking** — Records deleted in Tally persist forever in the
  DuckDB cache. Add diff-based deletion detection:
  1. During `full_sync()`, fetch all GUIDs from Tally for each entity type
  2. Compare against cached GUIDs — any GUID in cache but missing from Tally is deleted
  3. Delete orphaned records (cascade to child tables for vouchers)
  4. Log deletion counts at warning level
  Add a `detect_deletions()` method to `TallySyncEngine`.
  ```
  verify: uv run pytest tests/test_sync.py tests/test_cache.py -v
  commit: feat(sync): add deletion tracking via GUID diff during full_sync
  ```

- [x] **10h · Add multi-company filtering to MCP tools** — The `tally-mcp-server`
  reference passes `targetCompany` to 11 of 12 tools. Our MCP tools never filter by
  company. Add optional `company` parameter to all MCP tools (except `query_tally_data`),
  and filter queries by the active company when provided.
  ```
  verify: uv run pytest tests/test_mcp.py tests/test_query.py -v
  commit: feat(mcp): add company filtering parameter to all MCP tools
  ```

- [x] **10i · Integrate version gating in sync/connection flow** — `detect_tally_version()`
  and `capabilities()` exist in `version.py` but aren't called anywhere in the sync or
  connection flow. Integrate:
  1. Call `detect_tally_version()` on first successful connection
  2. Cache the result on `TallyConnection`
  3. Use `capabilities()` to gate: ALLLEDGERENTRIES.LIST (ERP 9 doesn't have it),
     base64 encoding (7.0+), JSON API (7.0+)
  4. Log detected version and capability set on startup
  ```
  verify: uv run pytest tests/test_sync.py tests/test_connection.py tests/test_version.py -v
  commit: feat(sync): integrate version detection and capability gating in sync flow
  ```

### Phase 10C — Documentation

- [x] **10j · Update SPECS.md with gap analysis findings** — Add new sections:
  - §14: Report parsing (Balance Sheet, P&L, Trial Balance response formats)
  - §15: Deletion tracking specification
  - §16: Multi-company MCP tool parameters
  - §17: Version gating integration
  - §18: Missing MCP tools specification
  - §19: ERP 9 vs TallyPrime parser differences
  - §20: Real Tally validation testing guidance
  ```
  verify: grep -c "§14" SPECS.md && grep -c "§20" SPECS.md
  commit: docs: add SPECS.md §14-§20 for production readiness gaps
  ```

- [x] **10k · Update RECOMMENDATIONS.md with new findings** — Add/update:
  - ALLLEDGERENTRIES.LIST vs LEDGERENTRIES.LIST analysis
  - fetch_report() half-built status and parser requirements
  - export_object() half-built status
  - Version gating unused — integration plan
  - Deletion tracking approach (diff vs _delete table)
  - Multi-company MCP tool gap
  ```
  verify: grep -c "ALLLEDGERENTRIES" RECOMMENDATIONS.md
  commit: docs: update RECOMMENDATIONS.md with gap analysis findings
  ```

- [x] **10l · Update CLAUDE.md with production readiness guidance** — Add:
  - Success metrics for v1.0 (0 mypy errors, 90%+ coverage, all Phase 10 done)
  - Real Tally testing guidance (how to set up test environment)
  - Version compatibility testing matrix
  ```
  verify: grep -c "v1.0 success metrics" CLAUDE.md
  commit: docs: add production readiness guidance to CLAUDE.md
  ```

---

## Done

When all boxes are checked through Phase 11, the project is ready for v1.0 release:

```bash
uv run mypy src/                  # 0 errors
uv run ruff check src/ tests/     # All checks passed
uv run pytest tests/ --cov=src/tallybridge --cov-fail-under=90 -q  # All pass, 90%+
git tag v1.0.0
git push --tags
# GitHub Actions publishes to PyPI automatically via publish.yml
```

---

## Phase 11 — JSON API, Import, BI Integration (Post-v1.0 Roadmap)

These tasks are planned but not yet started. They represent the next major
feature set based on the TallyPrime 7.0 JSON API documentation at
`https://help.tallysolutions.com/tally-prime-integration-using-json-1/`
and the TallyPrime API Explorer at `https://tallysolutions.com/tallyprime-api-explorer/`.

### Phase 11A — JSON API Support (TallyPrime 7.0+)

- [x] **11a · Add JSON request builders to TallyConnection** — Implement:
  1. `post_json(headers: dict, body: dict) -> dict` — POST JSON, return parsed dict
  2. `_build_collection_json()` — Build JSONEx collection request
  3. `_build_object_json()` — Build JSONEx object request
  4. `_build_report_json()` — Build JSONEx report request
  5. `_require_capability()` — Gate methods that need specific Tally versions
  6. `_get_export_format()` — Auto-select JSONEx (7.0+) or XML based on version
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add JSON request builders for TallyPrime 7.0+
  ```

- [x] **11b · Add TallyJSONParser** — Parallel parser for JSONEx responses:
  1. `parse_ledgers_json(data) -> list[TallyLedger]`
  2. `parse_groups_json(data) -> list[TallyGroup]`
  3. `parse_stock_items_json(data) -> list[TallyStockItem]`
  4. `parse_vouchers_json(data) -> list[TallyVoucher]`
  5. Same output types as TallyXMLParser — callers are format-agnostic
  ```
  verify: uv run pytest tests/test_parser.py -v
  commit: feat(parser): add TallyJSONParser for JSONEx responses
  ```

- [x] **11c · Auto-format selection in export methods** — When TallyPrime 7.0+
  is detected, `export_collection()`, `export_object()`, and `fetch_report()`
  automatically use JSON internally. Add `tally_export_format` config field
  (`"auto"`, `"xml"`, `"json"`). Update `TallyBridgeConfig` and docs.
  ```
  verify: uv run pytest tests/test_connection.py tests/test_sync.py -v
  commit: feat(connection): auto-select JSONEx export format for TallyPrime 7.0+
  ```

- [x] **11d · Integrate id-encoded header for multilingual** — Wire
  `encode_name_base64()` into request building when `supports_base64_encoding`
  is True. Add the `id-encoded` header to JSON requests with non-ASCII names.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): integrate base64 id-encoded header for multilingual
  ```

### Phase 11B — Import/Write-Back Capability

- [x] **11e · Add import_masters() and import_vouchers() to TallyConnection** —
  Implement XML import (works on all versions):
  1. `import_masters(data, company, format="xml") -> ImportResult`
  2. `import_vouchers(data, company, format="xml") -> ImportResult`
  3. `ImportResult` model with created/altered/deleted/error counts
  4. Safety: requires `TALLYBRIDGE_ALLOW_WRITES=true` env var
  5. Version gate JSON format: raise if `supports_json_api` is False
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add XML import for masters and vouchers
  ```

- [x] **11f · Add JSON import support** — When TallyPrime 7.0+ is detected,
  allow `format="json"` in import methods. Build JSON import request body
  per the official spec. Add `detailed-response` header support.
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add JSON import support for TallyPrime 7.0+
  ```

- [x] **11g · Add convenience methods for common imports** — High-level API:
  1. `create_ledger(name, parent_group, opening_balance, ...)`
  2. `create_voucher(voucher_type, date, ledger_entries, ...)`
  3. `cancel_voucher(guid)` — Set ISCANCELLED via alter
  4. Each method builds the XML/JSON payload internally
  ```
  verify: uv run pytest tests/test_connection.py -v
  commit: feat(connection): add convenience methods for ledger and voucher creation
  ```

### Phase 11C — BI Integration

- [x] **11h · Add pre-built SQL views for BI tools** — Add `VIEWS_SQL` constant
  in `cache.py` with BI-friendly views: `v_sales_summary`, `v_receivables`,
  `v_gst_summary`, `v_stock_summary`, `v_party_position`. Create views
  during `initialize()`.
  ```
  verify: uv run pytest tests/test_cache.py -v
  commit: feat(cache): add BI-friendly SQL views
  ```

- [x] **11i · Add docs/bi-integration.md** — Document how to connect:
  1. Power BI via DuckDB ODBC driver
  2. Metabase via native DuckDB driver
  3. Superset via DuckDB connector
  4. Looker via JDBC bridge
  5. Excel/Google Sheets via ODBC or CSV export
  ```
  verify: test -f docs/bi-integration.md
  commit: docs: add BI integration guide
  ```

- [x] **11j · Add `tallybridge serve` HTTP API bridge** — New CLI command that
   starts a read-only HTTP SQL API on the DuckDB file. Allows any HTTP-capable
   BI tool to query without DuckDB drivers.
  ```
  verify: uv run pytest tests/test_cli.py -v
  commit: feat(cli): add tallybridge serve command for HTTP API bridge
  ```

### Phase 11D — Documentation & Polish

- [x] **11k · Update README with JSON API, import, and BI sections** — Add:
  1. JSON API support note (TallyPrime 7.0+)
  2. Import/write-back API examples
  3. BI integration quick links
  4. `tally_export_format` config option
  5. `TALLYBRIDGE_ALLOW_WRITES` env var
  ```
  verify: grep -c "JSON API" README.md
  commit: docs: update README with JSON API, import, and BI sections
  ```

- [x] **11l · Update docs/mcp-setup.md with import tools** — Add new MCP
  tools for import operations (if `TALLYBRIDGE_ALLOW_WRITES` is enabled):
  `create_ledger`, `create_voucher`, `cancel_voucher`. Update tool table.
  ```
  verify: grep -c "create_ledger" docs/mcp-setup.md
  commit: docs: update MCP setup guide with import tools
  ```

---

## Phase 12 — GST Compliance & API Completeness (v1.1)

> **Source:** Ecosystem research comparing TallyBridge against user expectations,
> TallyPrime API capabilities, and competing libraries. Analysis covered GSTR
> returns, e-invoice/e-Way Bill, multi-currency, and API ergonomics.
> **Gate:** Phase 12A (P0 — GST critical) must complete before Phase 12B.
> **Spec:** Each task references a SPECS.md §26–§31 section.

### Phase 12A — P0: GST Compliance & Critical Gaps

- [x] **12a · Add GSTR-1 report fetching and parsing** — GSTR-1 (outward
  supplies) is the most critical GST return — it contains invoice-level
  details of all sales, filed monthly by every registered business.
  TallyBridge only has GSTR-3B (summary). Add:
  1. `GSTR1Invoice`, `GSTR1Section`, `GSTR1Result` models in `report.py`
  2. `"GSTR-1"` to `TallyReportType` literal
  3. `TallyXMLParser.parse_gstr1()` and `TallyJSONParser.parse_gstr1_json()`
  4. `TallyConnection.fetch_gstr1()` method
  5. `TallyQuery.get_gstr1()` method
  6. `get_gstr1` MCP tool
  7. Export models from `models/__init__.py` and `__init__.py`
  Spec: SPECS.md §26.
  ```
  verify: uv run pytest tests/test_parser.py tests/test_connection.py tests/test_query.py -v
  commit: feat(gstr1): add GSTR-1 outward supply report fetching and parsing
  ```

- [x] **12b · Add Godown entity to sync pipeline** — `TallyGodown` model
  exists but is never synced (missing from `ENTITY_CONFIG` and `SYNC_ORDER`).
  Godown names in inventory entries cannot be resolved. Add:
  1. `"godown"` entry to `ENTITY_CONFIG` with fields `NAME, GUID, ALTERID, PARENT`
  2. `"godown"` to `SYNC_ORDER` between `"cost_center"` and `"voucher"`
  3. `TallyXMLParser.parse_godowns()` and `TallyJSONParser.parse_godowns_json()`
  4. `mst_godown` table + `upsert_godowns()` in `cache.py` (migration 6)
  5. `TallyQuery.get_godown_summary()` method
  Spec: SPECS.md §27.
  ```
  verify: uv run pytest tests/test_sync.py tests/test_parser.py tests/test_cache.py -v
  commit: feat(sync): add Godown entity to sync pipeline with cache table
  ```

- [x] **12c · Add TallyBridge unified client (read + write)** — `connect()`
  returns `TallyQuery` (read-only). Write-back requires manual
  `TallyConnection` construction. Create a `TallyBridge` class that:
  1. Wraps `TallyCache`, `TallyConnection`, `TallySyncEngine`, `TallyQuery`
  2. Delegates all `TallyQuery` read methods
  3. Adds `create_ledger()`, `create_voucher()`, `cancel_voucher()` write methods
  4. Adds `sync()` method for on-demand syncing
  5. Supports `async with TallyBridge() as tb:` context manager
  6. Update `tallybridge.connect()` to return `TallyBridge` (non-breaking)
  7. Add `async with` context manager to `TallyConnection`
  Spec: SPECS.md §28.
  ```
  verify: uv run pytest tests/test_init.py tests/test_connection.py -v
  commit: feat(api): add TallyBridge unified client with read-write and context manager
  ```

### Phase 12B — P1: Professional Use Enhancements

- [x] **12d · Add pre-write validation layer** — `build_voucher_xml()`
  generates XML referencing ledgers that may not exist in Tally. Add
  `validate_voucher()` and `validate_ledger()` methods to `TallyBridge`
  that check the local cache before posting. Checks: ledger existence,
  balanced entries, party group membership, duplicate names. Add
  `ValidationResult` model. Integrate with `create_*` methods via
  `validate: bool = True` parameter.
  Spec: SPECS.md §29.
  ```
  verify: uv run pytest tests/test_init.py -v
  commit: feat(validate): add pre-write validation for voucher and ledger creation
  ```

- [x] **12e · Add GSTR-2A/2B ITC reconciliation** — ITC reconciliation is
  the second most common GST workflow. Add:
  1. `GSTR2AClaim` and `ReconciliationResult` models
  2. `TallyConnection.fetch_gstr2a()` method
  3. `TallyQuery.reconcile_itc()` method matching by GSTIN + invoice + date
  4. `reconcile_itc` MCP tool
  Spec: SPECS.md §30.
  ```
  verify: uv run pytest tests/test_connection.py tests/test_query.py -v
  commit: feat(gst): add GSTR-2A/2B ITC reconciliation support
  ```

- [x] **12f · Add multi-currency fields to voucher model** — Import/export
  businesses need forex gain/loss tracking. Add `currency`, `forex_amount`,
  `exchange_rate` to `TallyVoucher` and `TallyVoucherEntry`. Update
  `ENTITY_CONFIG` voucher fields. Update cache schema (migration 7).
  Spec: SPECS.md §31.
  ```
  verify: uv run pytest tests/test_parser.py tests/test_cache.py tests/test_models.py -v
  commit: feat(voucher): add multi-currency fields for forex tracking
  ```

### Phase 12C — P2: Advanced Features & Documentation

- [x] **12g · Add GSTR-9 annual return support** — GSTR-9 is required
  annually. Add `GSTR9Result` model, `fetch_gstr9()`, `parse_gstr9()`,
  and MCP tool. Follow the same pattern as GSTR-1 and GSTR-3B.
  ```
  verify: uv run pytest tests/test_parser.py tests/test_connection.py -v
  commit: feat(gst): add GSTR-9 annual return support
  ```

- [x] **12h · Update README and docs for Phase 12 features** — Add:
  1. GSTR-1, GSTR-2A, GSTR-9 examples in Python API section
  2. Godown sync note
  3. `TallyBridge` unified client examples (read + write)
  4. Multi-currency field documentation
  5. Pre-write validation documentation
  6. Update CHANGELOG.md with Phase 12 entries
  ```
  verify: grep -c "GSTR-1" README.md && grep -c "TallyBridge" README.md
  commit: docs: update README and docs for Phase 12 features
  ```

- [x] **12i · Final quality gate** — Ensure all Phase 12 code passes:
  ```
  uv run mypy src/              # 0 errors
  uv run ruff check src/ tests/ # All checks passed
  uv run pytest tests/ --cov=src/tallybridge --cov-fail-under=90 -q
  ```

---

## Phase 13 — E-Invoice, Data Export & Cloud Sync (v1.1)

> **Source:** Ecosystem research on e-invoice/e-Way Bill requirements (mandatory for Indian
> businesses with >₹5cr turnover), competitor analysis (tally-integration PyPI package),
> and gap analysis of existing TallyBridge features.
> **Gate:** Phase 13A (P0 — E-Invoice & Data Access) must complete before Phase 13B.
> **Spec:** Each task references a SPECS.md §32–§38 section (to be added).

### Phase 13A — P0: E-Invoice & E-Way Bill Data Access

- [x] **13a · Add e-invoice data fields to voucher model** — TallyPrime stores
  IRN (Invoice Reference Number), QR code, ACK number, and ACK date on each
  sales invoice that has been e-invoiced. These fields are critical for
  compliance verification and audit. Add:
  1. `irn`, `ack_number`, `ack_date`, `qr_code`, `is_einvoice` fields to `TallyVoucher`
  2. Update `ENTITY_CONFIG` voucher fields with `IRN`, `ACKNO`, `ACKDT`, `QRCODE`, `ISEINVOICE`
  3. Add parser support for these fields (XML tag names may vary by Tally version)
  4. Add cache migration (8) for new columns on `trn_voucher`
  5. Add `get_einvoice_summary()` method to `TallyQuery`
  6. Add `get_einvoice_status` MCP tool
  Spec: SPECS.md §32.
  ```
  verify: uv run pytest tests/test_parser.py tests/test_cache.py tests/test_models.py -v
  commit: feat(einvoice): add e-invoice IRN/QR/ACK fields to voucher model
  ```

- [x] **13b · Add e-Way Bill data fields to voucher model** — E-Way Bills are
  required for movement of goods exceeding ₹50,000. TallyPrime stores EWB
  number, date, validity, and vehicle/transporter details. Add:
  1. `eway_bill_number`, `eway_bill_date`, `eway_valid_till`, `transporter_name`,
     `vehicle_number`, `distance_km` fields to `TallyVoucher`
  2. Update `ENTITY_CONFIG` voucher fields
  3. Add parser support for e-Way Bill tags
  4. Add cache migration (9) for e-Way Bill columns on `trn_voucher`
  5. Add `get_eway_bill_summary()` method to `TallyQuery`
  6. Add `get_eway_bill_status` MCP tool
  Spec: SPECS.md §33.
  ```
  verify: uv run pytest tests/test_parser.py tests/test_cache.py tests/test_query.py -v
  commit: feat(ewaybill): add e-Way Bill fields to voucher model
  ```

- [x] **13c · Add e-invoice JSON export builder** — For the offline e-invoicing
  workflow, businesses need to export invoices in the IRP-compliant JSON format.
  TallyBridge should build the JSON payload from voucher data so users can:
  1. Validate invoice data before submission to IRP
  2. Export batch invoices for offline IRP upload
  3. Pre-fill e-invoice fields from Tally data
  Add `EInvoiceBuilder` class with `build_einvoice_json(voucher)` method.
  Follow NIC's e-invoice JSON schema (version 1.1).
  Spec: SPECS.md §34.
  ```
  verify: uv run pytest tests/test_einvoice.py -v
  commit: feat(einvoice): add IRP-compliant JSON export builder
  ```

### Phase 13B — P1: Data Export & Audit

- [ ] **13d · Add data export module (CSV, Excel, JSON)** — Users need to
  export cached Tally data for analysis, sharing, and backup. Add:
  1. `src/tallybridge/export.py` with `DataExporter` class
  2. `export_csv(table, path, filters)` — Export any cache table to CSV
  3. `export_excel(tables, path)` — Export multiple tables to Excel sheets
  4. `export_json(table, path, filters)` — Export as JSON
  5. CLI commands: `tallybridge export csv --table ledgers --output ledgers.csv`
  6. MCP tool: `export_data` for on-demand export
  Spec: SPECS.md §35.
  ```
  verify: uv run pytest tests/test_export.py -v
  commit: feat(export): add CSV/Excel/JSON data export module
  ```

- [ ] **13e · Add audit logging for write operations** — Track all data
  modifications for compliance and debugging. Add:
  1. `audit_log` table in cache schema (migration 10): timestamp, operation,
     entity_type, entity_guid, user, details_json
  2. `log_audit()` method on `TallyCache`
  3. Auto-log all `import_masters()`, `import_vouchers()`, `create_*()`,
     `cancel_voucher()` operations
  4. `get_audit_log()` query method with date/entity filters
  5. `get_audit_log` MCP tool
  Spec: SPECS.md §36.
  ```
  verify: uv run pytest tests/test_cache.py tests/test_mcp.py -v
  commit: feat(audit): add audit logging for all write operations
  ```

- [ ] **13f · Add scheduled report generation** — Businesses need automated
  daily/weekly/monthly reports. Add:
  1. `src/tallybridge/reports.py` with `ReportScheduler` class
  2. Template-based report generation (daily digest, GST summary, receivables)
  3. `add_schedule(report_type, frequency, output_format, output_path)` method
  4. CLI commands: `tallybridge report schedule --type daily --frequency daily`
  5. Integration with `run_continuous()` for periodic report generation
  6. Optional email alerts (SMTP config in settings)
  Spec: SPECS.md §37.
  ```
  verify: uv run pytest tests/test_reports.py -v
  commit: feat(reports): add scheduled report generation
  ```

### Phase 13C — P2: Cloud Sync & Polish

- [ ] **13g · Implement Supabase cloud sync** — Replace the `cloud/supabase.py`
  stub with a working cloud sync module. Add:
  1. `CloudSync` class with incremental upload/download
  2. Conflict resolution strategy (last-write-wins with audit trail)
  3. Multi-device sync via Supabase Realtime
  4. Auth integration with Supabase Auth
  5. `tallybridge cloud sync` CLI command
  6. Rate limiting and retry logic
  Spec: SPECS.md §38.
  ```
  verify: uv run pytest tests/test_cloud.py -v
  commit: feat(cloud): implement Supabase cloud sync
  ```

- [ ] **13h · Performance optimization for large datasets** — Optimize for
  companies with 100k+ vouchers:
  1. Streaming/lazy loading for large query results
  2. Chunked export for CSV/Excel (avoid loading all data in memory)
  3. Connection pooling improvements
  4. Add query result caching with configurable TTL
  5. Add `EXPLAIN ANALYZE` to slow query logging
  6. Benchmark suite in `tests/bench/`
  ```
  verify: uv run pytest tests/ -v
  commit: perf: optimize for large dataset handling
  ```

- [ ] **13i · Final quality gate and documentation** — Ensure all Phase 13
  code passes quality checks and update all documentation:
  1. `mypy src/` — 0 errors
  2. `ruff check src/ tests/` — All checks passed
  3. `pytest tests/ --cov=src/tallybridge --cov-fail-under=90` — 90%+ coverage
  4. Update README.md with e-invoice, e-Way Bill, export, cloud sync sections
  5. Update CHANGELOG.md with Phase 13 entries
  6. Update SPECS.md with §32–§38 sections
  7. Update `pyproject.toml` version to `1.1.0`
  ```
  verify: uv run mypy src/ && uv run ruff check src/ tests/ && uv run pytest tests/ --cov=src/tallybridge --cov-fail-under=90 -q
  commit: docs: finalize Phase 13 documentation and quality gate
  ```
