## [Unreleased]

### Added — Phase 10A: Production Readiness

- **10c**: Improve test coverage from 85% to 93.45% (428 tests). Coverage by module: sdk_server.py 95%, sync.py 97%, parser.py 96%, version.py 90%, query.py 91%, cache.py 91%, connection.py 89%, cli.py 90%

### Added — Phase 9A: Correctness & Security

- **9a**: Catch `httpx.ReadTimeout` in `connection.py:post_xml()` and raise `TallyConnectionError` with timeout value and batch size suggestion
- **9b**: Remove `date.today()` fallback in `parser.py:parse_vouchers()` and `parse_outstanding_bills()`, and in `cache.py:_get_outstanding()` — now skips records with unparseable dates and logs a warning
- **9c**: Add `strict_status: bool = False` config field, debug logging for STATUS=0 responses, code comment block documenting STATUS semantics discrepancy between official docs and observed TallyPrime behavior
- **9d**: Add `_ensure_company()` method to `TallySyncEngine` — auto-detects company on first call and always includes `SVCURRENTCOMPANY` in subsequent requests; warns when operating without a company
- **9e**: Replace `BEGIN READ ONLY` fallback with true DuckDB read-only connection using suspend/resume write connection pattern in `cache.py:query_readonly()`
- **9f**: `upsert_vouchers()` now returns `(count, max_committed_alter_id)` tuple; `sync_entity()` advances sync_state only to highest successfully committed alter_id
- **9g**: Add `tenacity` retry decorator to `post_xml()` with exponential backoff on `httpx.ReadTimeout` and transient `TallyDataError` (max 3 retries, 1s–10s wait)
- **9h**: Add `mcp_api_key: str | None = None` config field; validate `Bearer` token for HTTP transport in MCP server; warn when HTTP mode has no key set

### Added — Phase 9B: Data Integrity & Performance

- **9i**: Add `reconcile=True` parameter to `sync_all()`, `_reconcile_counts()` method comparing cache counts vs sync results
- **9j**: Add `content_hash` column (SHA-256) to all 7 master tables via migration 4; `detect_content_drift()` and `compare_content_drift()` methods for snapshot-based drift detection; integrated into `full_sync()`
- **9k**: Add `reconcile_orphans()` method to `TallyCache` detecting orphaned ledger entries; integrated into `health_check()`
- **9l**: Convert all master `upsert_*()` methods from row-by-row `execute()` to `executemany()` for 10–100x performance on large batches
- **9m**: Add `_sync_master_batched()` method to `TallySyncEngine` — applies AlterID-range batching to master entities when alter_id range exceeds threshold
- **9n**: Add `voucher_batch_size` to `TallyBridgeConfig` (default 5000, max 10000); `TallySyncEngine` uses config value
- **9o**: Consolidate 10 separate COUNT queries in `health_check()` into single `UNION ALL` query

### Added — Phase 9C: Feature Completeness

- **9p**: Add `encode_name_base64()` static method to `TallyConnection` for base64-encoding multilingual entity names (TallyPrime 7.0+ `id-encoded` header support)
- **9q**: Add `export_object()` method to `TallyConnection` using TYPE=Object XML pattern; supports lookup by Name or GUID
- **9r**: Add `fetch_report()` method to `TallyConnection` using TYPE=Data XML pattern; supports Balance Sheet, P&L, Trial Balance, Day Book
- **9s**: Add `capabilities()` method and new properties (`supports_json_api`, `supports_base64_encoding`, `supports_tally_drive`) to `TallyProduct` for version-aware feature gating
- **9t**: Enhance `search()` in `TallyQuery` with trigram-based fuzzy matching using DuckDB's `similarity()` function; falls back to ILIKE when unavailable

### Added — Phase 9D: Developer Experience & Reliability

- **9u**: Add circuit breaker to `run_continuous()` with exponential backoff (doubles on failure, max 60 min, resets on success)
- **9v**: Add graceful shutdown via `_shutdown_event` asyncio.Event, `request_shutdown()` method, SIGINT/SIGTERM signal handlers
- **9w**: Document TallyPrime API Explorer and Integration Demo Samples in `docs/tally-setup.md`
- **9x**: Add feature compatibility matrix (Tally.ERP 9, TallyPrime 1.x–3.x, 4.x–6.x, 7.0+) to `docs/tally-setup.md`
- **9y**: Add SSH tunnel setup guide and plaintext data warning for remote Tally access to `docs/tally-setup.md`
- **9z**: Add `sync_errors` table via migration 5; `log_sync_error()` and `get_sync_errors()` methods; `get_sync_errors` MCP tool

## [0.1.0] - 2026-04-26

### Added

- **Six-layer architecture**: MCP → CLI → Query → Cache → Sync → Parser → Connection
- **TallyConnection**: Async HTTP client with transport-level retries, configurable encoding (UTF-8/UTF-16), XML entity escaping, EXCEPTION/STATUS/LINEERROR response checking
- **TallyXMLParser**: Parse ledgers, groups, stock items, vouchers, units, stock groups, cost centers from Tally XML; handles both LEDGERENTRIES.LIST and ALLLEDGERENTRIES.LIST, BILLALLOCATIONS.LIST with complex BILLCREDITPERIOD (INDAYS + DUEONDATE fallback), COSTCENTRE.LIST with CATEGORYALLOCATIONS.LIST
- **TallyCache**: DuckDB-backed cache with upsert methods, AlterID-based sync state, read-only query enforcement via BEGIN READ ONLY transactions, Decimal precision preserved (no float conversion)
- **TallySyncEngine**: AlterID-based incremental sync, batched voucher fetching (5000/batch), full sync, continuous sync with asyncio.Lock, company parameter support, auto-detect active company
- **TallyQuery**: Daily digest, receivables, payables, sales/purchases summary, stock aging, GST summary, cost center summary, search, party outstanding
- **TallyProduct version detection**: Auto-detect Tally.ERP 9 vs TallyPrime (1.x–7.x) via $$SysInfo:Version TDL query, with compatibility properties per version
- **MCP Server**: Official SDK-based (FastMCP) server with 12 tool definitions, lifespan pattern, tool annotations (readOnlyHint, openWorldHint), CallToolResult error handling, query_readonly() SQL safety
- **CLI**: Typer-based with init wizard, sync, status, doctor, mcp, config, --version commands; uses SDK MCP server
- **Models**: Pydantic v2 models for all entities including TallyCostCentreAllocation and TallyBillAllocation
- **Exception hierarchy**: TallyConnectionError, TallyDataError, TallySyncError, TallyBridgeCacheError
- **Config**: pydantic-settings with env var overrides, configurable encoding, singleton get_config()
- **Tests**: 285 tests passing, mock Tally HTTP server, no real Tally needed
- **Docs**: tally-setup.md, mcp-setup.md with correct tallybridge-mcp entry point
- **Recipes**: daily_digest.py, overdue_receivables.py, gst_mismatch_alert.py, anomaly_detector.py
