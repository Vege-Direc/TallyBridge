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

- [ ] **__init__.py** — Implement the stable public API contract. Spec: SPECS.md §12. Include the `connect()` convenience function.
  ```
  verify: uv run python -c "import tallybridge; print(tallybridge.__version__)"
  commit: feat: expose stable public API in __init__.py
  ```

- [ ] **Integration tests** — Write `tests/test_integration.py`: full end-to-end flow using mock_tally → sync_all → query. Spec: SPECS.md §11c.
  ```
  verify: uv run pytest tests/test_integration.py -v
  commit: test: add end-to-end integration tests
  ```

---

## Phase 6 — Recipes and Docs

- [ ] **recipes/** — Write all four recipe scripts. Spec: SPECS.md §13. Each must run standalone and fail gracefully when Tally is not connected.
  ```
  verify: uv run python recipes/daily_digest.py 2>&1 | grep -E "(sales|Could not connect)"
  commit: feat(recipes): add daily digest, receivables, GST, and anomaly detector
  ```

- [ ] **docs/** — Write `docs/tally-setup.md` (how to enable Tally HTTP server) and `docs/mcp-setup.md` (claude_desktop_config.json setup). Update `README.md` with `connect()` quickstart.
  ```
  verify: cat docs/tally-setup.md | grep "9000"   # confirm port mentioned
  commit: docs: add Tally setup guide and MCP connection guide
  ```

---

## Phase 7 — Polish and Release Prep

- [ ] **Linting** — Run `uv run ruff check src/ tests/` and fix every reported issue. Run `uv run ruff format src/ tests/`.
  ```
  verify: uv run ruff check src/ tests/   # must output: All checks passed.
  commit: style: fix all ruff lint and format issues
  ```

- [ ] **Type checking** — Run `uv run mypy src/` and fix all type errors. Add `# type: ignore[<code>]` only for genuine third-party stub gaps, with a comment explaining why.
  ```
  verify: uv run mypy src/   # must output: Success: no issues found
  commit: fix(types): resolve all mypy type errors
  ```

- [ ] **Full test suite + coverage** — Run all tests with coverage. Fix any gaps below target.
  ```
  verify: uv run pytest tests/ --cov=src/tallybridge --cov-fail-under=90 -v
  commit: test: achieve 90%+ overall coverage
  ```

- [ ] **Build verification** — Build the package and verify the wheel installs cleanly.
  ```
  verify: uv build && pip install dist/tallybridge-0.1.0-*.whl --dry-run
  commit: chore: confirm package builds and installs correctly
  ```

- [ ] **CHANGELOG + version** — Write `CHANGELOG.md` entry for v0.1.0. Confirm `pyproject.toml` version is `0.1.0`. Confirm all GitHub URLs reference the real repo.
  ```
  verify: grep "0.1.0" CHANGELOG.md pyproject.toml src/tallybridge/__init__.py
  commit: chore: finalise v0.1.0 release metadata
  ```

---

## Done

When all boxes are checked, the project is ready to tag and release:

```bash
git tag v0.1.0
git push --tags
# GitHub Actions publishes to PyPI automatically via publish.yml
```
