## [Unreleased]

### Added — Phase 12: GST Reports, Multi-Currency, Validation

- **12a**: Add GSTR-1 outward supply report fetching and parsing (`fetch_gstr1()`, `parse_gstr1()`, `GSTR1Result` model)
- **12b**: Add Godown entity to sync pipeline with cache table (`TallyGodown` model, `mst_godown` table, migration 6)
- **12c**: Add TallyBridge unified client with read-write and context manager — single object for sync, query, validation, and write-back
- **12d**: Add pre-write validation layer — `validate_voucher()` and `validate_ledger()` methods check cache before posting; `ValidationResult` model; `validate: bool = True` parameter on `create_voucher()` and `create_ledger()`; raises `TallyDataError` on validation failure
- **12e**: Add GSTR-2A/2B ITC reconciliation — `GSTR2AClaim` model, `fetch_gstr2a()`, `reconcile_itc()` query method (matches by GSTIN+voucher number with fallback), `reconcile_itc` MCP tool
- **12f**: Add multi-currency fields to voucher model — `currency`, `forex_amount`, `exchange_rate`, `base_currency_amount` on `TallyVoucher`; `currency`, `forex_amount`, `exchange_rate` on `TallyVoucherEntry`; cache migration 7
- **12g**: Add GSTR-9 annual return support — `GSTR9Result` and `GSTR9Section` models, `fetch_gstr9()`, `parse_gstr9()` (flush-section pattern), `get_gstr9` MCP tool

### Added — Phase 11E: HTTP API Bridge

- **11j**: Add `tallybridge serve` CLI command starting a read-only HTTP SQL API bridge using FastAPI. Endpoints: `GET /` (info), `GET /health`, `GET /views` (list BI views), `GET /views/{name}` (query a view), `POST /query` (execute read-only SQL), `GET /tables` (list tables). Includes CORS middleware, SQL injection prevention (keyword blocklist + DuckDB read-only connection), and pagination on view queries. Requires `pip install tallybridge[serve]` for FastAPI/uvicorn

### Added — Phase 9E Completion

- **9ae**: Add `fetch_gstr3b()` method to `TallyConnection` using TYPE=Data report pattern with report name "GSTR 3B". Add `GSTR3BResult` and `GSTR3BSection` models. Add `parse_gstr3b()` to `TallyXMLParser` and `parse_gstr3b_json()` to `TallyJSONParser` for structured section extraction (taxable value, IGST, CGST, SGST, Cess)
- **9af**: Parallel master entity syncing — `sync_all()` now uses `asyncio.gather()` to sync all 7 master entities concurrently, then syncs vouchers sequentially after masters complete
- **9aj**: Add TSS renewal prompt to `tallybridge doctor` — when TallyPrime 7.0+ features are unavailable, displays a yellow message with renewal URL (tallysolutions.com) and current version info

### Added — Phase 11D: Documentation

- **11i**: Add `docs/bi-integration.md` with connection guides for Power BI, Metabase, Superset, Looker, Excel, and direct SQL access. Includes schema reference and tips
- **11l**: Update `docs/mcp-setup.md` with import/write-back tools section (`create_ledger`, `create_voucher`, `cancel_voucher`) requiring `TALLYBRIDGE_ALLOW_WRITES=true`

### Added — Phase 11B: Import/Write-Back Capability

- **11e**: Add `import_masters()` and `import_vouchers()` XML import methods to `TallyConnection`. Requires `TALLYBRIDGE_ALLOW_WRITES=true` env var. Add `ImportResult` model with created/altered/deleted/errors counts. Add `_parse_import_response_xml()` and `_check_writes_allowed()` helpers. Add `allow_writes: bool = False` config field
- **11f**: Add `import_masters_json()` and `import_vouchers_json()` for TallyPrime 7.0+ JSON import. Add `_build_import_json()` with `detailed-response` header and `svmstimportformat`/`svvchimportformat` static variables. Add `_parse_import_response_json()` for JSON import response parsing
- **11g**: Add convenience methods: `build_ledger_xml()`, `build_voucher_xml()`, `build_cancel_voucher_xml()`, `build_ledger_json()`, `build_voucher_json()`, `build_cancel_voucher_json()`. Each builds the data payload for import operations

### Added — Phase 9E: TallyPrime 7.0 Low-Hanging Fruit

- **9ac**: Add `_fix_currency_entities()` to `TallyXMLParser` — replaces AED (`&#8387;` → U+20C3) and SAR (`&#8385;` → U+20C1) entity codes that may not decode correctly in ElementTree. Handles TallyPrime 7.0 currency symbol changes
- **9ai**: `SVExportInPlainFormat` already set to `Yes` in `_build_report_json()` for cleaner JSON report output without TDL metadata wrappers
- **9ag**: Add TSS expiry status detection to `tallybridge doctor` command — queries Tally version and reports whether TallyPrime 7.0+ features are available

### Added — Phase 11C: BI Integration

- **11h**: Add 5 pre-built SQL views for BI tools: `v_sales_summary`, `v_receivables`, `v_gst_summary`, `v_stock_summary`, `v_party_position`. Views are created automatically during `TallyCache.initialize()`. Compatible with Power BI, Metabase, Superset via DuckDB ODBC/native drivers

### Added — Phase 11A: JSON API Support (TallyPrime 7.0+)

- **11a**: Add `tally_export_format` config field (`auto`, `xml`, `json`) — when `auto`, uses JSONEx on TallyPrime 7.0+, XML otherwise. Add `post_json()` method to `TallyConnection` with same retry/error handling as `post_xml()`. Add `_build_collection_json()`, `_build_object_json()`, `_build_report_json()` builder methods producing HTTP headers + JSON body per TallyPrime 7.0 spec. Add `_require_capability()` and `_get_export_format()` helpers. Add `id-encoded` header for non-ASCII names in JSON object requests. Modify `export_collection()`, `export_object()`, `fetch_report()` for auto-format selection
- **11b**: Add `TallyJSONParser` class producing the same Pydantic model types as `TallyXMLParser`. Handles JSONEx response structure (`data.tallymessage` array, lowercase keys, `.list` suffix for sub-collections). Reuses `parse_amount`/`parse_date`/`parse_bool` from XML parser. Supports all entity types: ledgers, groups, stock items, stock groups, units, voucher types, cost centres, vouchers, and reports
- **11c**: Add auto-format selection in `TallySyncEngine._parse_entity()` — detects `isinstance(response, dict)` and routes to `_parse_entity_json()` which uses `TallyJSONParser`. Return type of `export_collection()` is now `str | dict`
- **11d**: Wire `encode_name_base64()` into JSON request building — `_build_object_json()` adds `id-encoded` header for non-ASCII names when `supports_base64=True`, `_build_collection_json()` adds `id-encoded` for non-ASCII company names
- **11a-tests**: Add JSON mock data (`SAMPLE_LEDGERS_JSON`, `SAMPLE_VOUCHERS_JSON`, etc.) and extend mock server to detect `Content-Type: application/json` and return JSON responses. Add 30+ tests covering JSON parser, JSON connection methods, config validation, sync engine JSON routing

### Added — Phase 10A: Production Readiness

- **10c**: Improve test coverage from 85% to 93.45% (428 tests). Coverage by module: sdk_server.py 95%, sync.py 97%, parser.py 96%, version.py 90%, query.py 91%, cache.py 91%, connection.py 89%, cli.py 90%
- **10d**: Add report response parsers: `parse_report()` auto-detects report type, `parse_balance_sheet()` (BSNAME/BSCLOSAMT), `parse_profit_loss()` (PLNAME/PLCLOSAMT), `parse_trial_balance_report()` (DSPACCNAME/DSPACCINFO), `parse_day_book_report()` (VOUCHER). New models: `ReportLine`, `TallyReport`, `TallyReportType`. `fetch_report(parse=True)` returns structured `TallyReport`
- **10e**: Add `parse=True` parameter to `export_object()` that auto-detects object type and routes to the appropriate parser method (parse_ledgers, parse_vouchers, etc.) returning typed model instances
- **10f**: Add 4 MCP tools: `get_balance_sheet`, `get_profit_loss`, `get_ledger_account`, `get_stock_item_account`. Corresponding query methods added to `TallyQuery`. Tool count: 13 → 17
- **10g**: Add deletion tracking: `detect_deletions()` in `TallySyncEngine` fetches all GUIDs from Tally, compares against cache, deletes orphans with cascade for vouchers. `get_cached_guids()` and `delete_records_by_guid()` in `TallyCache`. Integrated into `full_sync()`
- **10h**: Add optional `company` parameter to all 15 MCP tools (except `query_tally_data` which uses SQL directly)
- **10i**: Add `detect_version()` method on `TallyConnection` that calls `detect_tally_version()` and logs the capability set. Sync engine uses `connection.detect_version()` instead of importing `detect_tally_version` directly
- **10j**: Add SPECS.md §14–§20: Report parsing, deletion tracking, multi-company MCP tools, version gating, missing MCP tools, ERP 9 differences, real Tally validation
- **10k**: Update RECOMMENDATIONS.md with Phase 10 gap analysis findings: ALLLEDGERENTRIES.LIST vs LEDGERENTRIES.LIST, fetch_report()/export_object() parsing, version gating integration, deletion tracking, multi-company MCP gap
- **10l**: Add v1.0 success metrics, real Tally testing guidance, and version compatibility matrix to CLAUDE.md

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
