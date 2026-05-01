# Changelog

All notable changes to TallyBridge will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed — TallyHelp Official Docs Compliance & UX

- **XML format**: Fix `<TALLYREQUEST>` values to match official TallyHelp documentation — changed from `"Export Data"` / `"Import Data"` to `"Export"` / `"Import"` across all XML builders (ping, collection, object, report, import). The previous values worked due to Tally's lenient parsing but were not per spec.
- **Import XML structure**: Restructured `import_masters()` and `import_vouchers()` to match official TallyHelp Case Study format — added `<TYPE>Data</TYPE>` and `<ID>All Masters</ID>` / `<ID>Vouchers</ID>` to header; replaced `<IMPORTDATA><REQUESTDESC><REQUESTDATA>` body structure with `<DESC><STATICVARIABLES>` + `<DATA><TALLYMESSAGE>` per current docs.
- **Import duplicates control**: Added `import_dups` parameter to `import_masters()` and `import_vouchers()` supporting `@@DUPCOMBINE` (default), `@@DUPMODIFY`, `@@DUPIGNORE`, `@@DUPIGNORECOMBINE` as documented in TallyHelp import reference.
- **Object export format**: Fixed `_build_object_xml()` to use official TallyHelp format — added `<SUBTYPE>` tag and changed object identifier from `<SVOBJECTNAME>` to `<ID TYPE="Name">` / `<ID TYPE="GUID">` per docs.
- **Error messages**: Updated connection error messages to include both TallyPrime 7.0+ (`F1 > Help > Settings > Advanced Configuration`) and older (`F1 > Settings > Connectivity`) navigation paths.
- **`tallybridge setup` command**: New auto-detection setup wizard that scans ports 9000/9001/9090 for TallyPrime, lists available companies, and writes configuration to `.env`. Replaces the simpler `init` command (which now aliases to `setup`).
- **`tally_check_connection` MCP tool**: New tool that tests TallyPrime connectivity, detects version, lists companies, and provides setup suggestions on failure — designed for AI assistants to troubleshoot connection issues.
- **`tally_setup_guide` MCP tool**: New tool that returns version-specific step-by-step TallyPrime HTTP configuration instructions — designed for AI assistants helping users with first-time setup.
- **Mock server**: Updated test mock to match new import XML format (`"Import"` instead of `"Import Data"`).

### Added — Phase 13: E-Invoice, Export, Audit, Reports, Performance

- **13a**: Add e-invoice and e-Way Bill fields to `TallyVoucher` model — `irn`, `irn_date`, `eway_bill_number`, `eway_bill_date`, `eway_bill_valid_till`, `transporter_name`, `vehicle_number`, `distance_in_km`; cache migration 8
- **13b**: Add e-invoice JSON export builder — `build_einvoice_json()` on `TallyConnection` generates NIC-compliant e-invoice v1.1 JSON from voucher data
- **13c**: Add e-invoice and e-Way Bill summary queries — `get_einvoice_summary()` and `get_eway_bill_summary()` on `TallyQuery`; MCP tools `get_einvoice_status` and `get_eway_bill_status`
- **13d**: Add data export module — `DataExporter` class with `export_csv()`, `export_excel()` (multi-sheet, requires `openpyxl`), `export_json()`, `export_csv_chunked()` (memory-efficient for 100k+ rows); CLI commands `tallybridge export csv/excel/json`; MCP tool `export_data`; `[excel]` optional dependency
- **13e**: Add audit logging — `audit_log` table (migration 10) tracking all write operations; `TallyCache.log_audit()` and `get_audit_log()`; auto-logging on `create_ledger()`, `create_voucher()`, `cancel_voucher()` via `TallyBridge` client; MCP tool `get_audit_log`
- **13f**: Add scheduled report generation — `ReportScheduler` class with `generate_report()` (daily_digest, gst_summary, receivables, payables, stock_summary, einvoice_summary), `add_schedule()`, `run_pending()`, `run_scheduled()`, `send_email()`; CLI command `tallybridge report generate`
- **13h**: Add performance optimization — query result caching with configurable TTL (`query_cache_ttl`); slow query logging (`slow_query_threshold`); `query_iter()` for memory-efficient chunked iteration; `export_csv_chunked()` for large dataset export; cache invalidation on all upsert operations; config fields `query_cache_ttl`, `slow_query_threshold`, `export_chunk_size`

### Added — Phase 12: GST Reports, Multi-Currency, Validation

- **12a**: Add GSTR-1 outward supply report fetching and parsing — `fetch_gstr1()`, `parse_gstr1()`, `GSTR1Result` model
- **12b**: Add Godown entity to sync pipeline — `TallyGodown` model, `mst_godown` table, migration 6
- **12c**: Add TallyBridge unified client — single object for sync, query, validation, and write-back with `async with` context manager
- **12d**: Add pre-write validation layer — `validate_voucher()` and `validate_ledger()` methods check cache before posting; `ValidationResult` model; `validate: bool = True` parameter
- **12e**: Add GSTR-2A/2B ITC reconciliation — `GSTR2AClaim` model, `fetch_gstr2a()`, `reconcile_itc()` query method; `reconcile_itc` MCP tool
- **12f**: Add multi-currency fields — `currency`, `forex_amount`, `exchange_rate`, `base_currency_amount` on `TallyVoucher` and `TallyVoucherEntry`; cache migration 7
- **12g**: Add GSTR-9 annual return support — `GSTR9Result` and `GSTR9Section` models, `fetch_gstr9()`, `parse_gstr9()`; `get_gstr9` MCP tool

### Added — Phase 11: JSON API, Import, BI Integration

- **11a**: Add JSON request/response support for TallyPrime 7.0+ — `post_json()`, `_build_collection_json()`, `_build_object_json()`, `_build_report_json()`, `_require_capability()`, `_get_export_format()`; `tally_export_format` config field
- **11b**: Add `TallyJSONParser` — Parallel parser for JSONEx responses producing the same Pydantic model types as `TallyXMLParser`
- **11c**: Add auto-format selection in sync engine — detects JSON responses and routes to JSON parser
- **11d**: Add `id-encoded` header support — base64-encoded names for non-ASCII entity lookups
- **11e**: Add XML import methods — `import_masters()`, `import_vouchers()` with `ImportResult` model; requires `TALLYBRIDGE_ALLOW_WRITES=true`
- **11f**: Add JSON import methods — `import_masters_json()`, `import_vouchers_json()` for TallyPrime 7.0+ with `detailed-response` header
- **11g**: Add convenience methods — `build_ledger_xml()`, `build_voucher_xml()`, `build_cancel_voucher_xml()`, `build_ledger_json()`, `build_voucher_json()`, `build_cancel_voucher_json()`
- **11h**: Add 5 pre-built SQL views for BI tools — `v_sales_summary`, `v_receivables`, `v_gst_summary`, `v_stock_summary`, `v_party_position`
- **11i**: Add `docs/bi-integration.md` — Connection guides for Power BI, Metabase, Superset, Looker, Excel
- **11j**: Add `tallybridge serve` CLI command — Read-only HTTP SQL API bridge using FastAPI (requires `pip install tallybridge[serve]`)
- **11k**: Update README with JSON API, import, and BI sections
- **11l**: Update `docs/mcp-setup.md` with import/write-back tools section

### Added — Phase 10: Production Readiness

- **10a**: Fix all mypy type errors (76 → 0) across `sdk_server.py`, `cache.py`, `version.py`
- **10b**: Add `LEDGERENTRIES.LIST` fallback for Tally.ERP 9 compatibility in parser
- **10c**: Improve test coverage to 93%+ (428 tests)
- **10d**: Add report response parsers — `parse_report()`, `parse_balance_sheet()`, `parse_profit_loss()`, `parse_trial_balance_report()`, `parse_day_book_report()`; `TallyReport` and `ReportLine` models
- **10e**: Add `parse=True` parameter to `export_object()` returning typed model instances
- **10f**: Add 4 MCP tools — `get_balance_sheet`, `get_profit_loss`, `get_ledger_account`, `get_stock_item_account`
- **10g**: Add deletion tracking — `detect_deletions()` compares cached GUIDs vs Tally; cascade delete for voucher child tables
- **10h**: Add optional `company` parameter to all MCP tools
- **10i**: Integrate version detection in sync/connection flow — auto-detect and log capability set on first sync

### Added — Phase 9: Analysis-Driven Improvements

- **9a**: Catch `httpx.ReadTimeout` in `post_xml()` and raise `TallyConnectionError`
- **9b**: Remove `date.today()` fallback in `parse_vouchers()` and `_get_outstanding()` — skip records with unparseable dates instead
- **9c**: Add `strict_status` config field and debug logging for STATUS=0 responses
- **9d**: Always include `SVCURRENTCOMPANY` after first company detection in sync engine
- **9e**: Use separate DuckDB read-only connection for `query_readonly()` — no fallback to read-write
- **9f**: Track highest successfully committed alter_id — only advance sync_state to committed value
- **9g**: Add `tenacity` retry with exponential backoff on `ReadTimeout` and transient errors
- **9h**: Add API key authentication for MCP HTTP transport — `mcp_api_key` config field
- **9i**: Add record count reconciliation after sync — `reconcile=True` parameter on `sync_all()`
- **9j**: Add `content_hash` column (SHA-256) for drift detection on all master tables — migration 4
- **9k**: Add `reconcile_orphans()` for detecting orphaned ledger entries
- **9l**: Convert all upsert methods to `executemany()` for 10–100x batch performance
- **9m**: Add AlterID-range batching for master entities exceeding threshold
- **9n**: Make `voucher_batch_size` configurable (default 5000, max 10000)
- **9o**: Consolidate health_check COUNT queries into single UNION ALL
- **9p**: Add `encode_name_base64()` for multilingual entity name encoding
- **9q**: Add `export_object()` for single-record lookups via TYPE=Object XML pattern
- **9r**: Add `fetch_report()` for Balance Sheet, P&L, Trial Balance, Day Book
- **9s**: Add version-aware feature gating — `TallyProduct.capabilities()` and `supports_*` properties
- **9t**: Add trigram fuzzy search to `query.search()` with ILIKE fallback
- **9u**: Add circuit breaker with exponential backoff to `run_continuous()`
- **9v**: Add graceful shutdown via `asyncio.Event` and signal handlers
- **9w**: Document TallyPrime API Explorer and Integration Demo Samples
- **9x**: Add feature compatibility matrix to `docs/tally-setup.md`
- **9y**: Add SSH tunnel setup guide to `docs/tally-setup.md`
- **9z**: Add `sync_errors` table for tracking failed records; `get_sync_errors` MCP tool
- **9ae**: Add `fetch_gstr3b()` method using TYPE=Data report pattern
- **9af**: Add parallel master entity syncing via `asyncio.gather()`
- **9ag**: Add TSS renewal prompt to `tallybridge doctor` command
- **9ai**: Add `SVExportInPlainFormat` support for JSON report exports
- **9ac**: Add `_fix_currency_entities()` for AED/SAR entity code handling
- **9ad**: Add import (write) capability via XML and JSON formats

### Added — Phase 8: Recommendations v2 Implementation

- **8a**: Remove all `float()` conversions in cache.py — preserve DECIMAL precision
- **8b**: Add XML entity escaping via `html.escape()` in connection.py
- **8c**: Add `<EXCEPTION>` prefix and `<STATUS>` tag checking to `post_xml()`
- **8d**: Replace `is_safe_sql()` with DuckDB read-only connection for query tool
- **8e**: Add configurable encoding — `tally_encoding` config field; align request/response encoding
- **8f**: Use httpx transport-level retries instead of tenacity for TCP errors
- **8g**: Implement batched voucher fetching with AlterID ranges (batch size 5000)
- **8h**: Add company selection and multi-company tracking — auto-detect active company
- **8i**: Implement `trn_cost_centre` and `trn_bill` tables with parser support
- **8j**: Rewrite MCP server using official `mcp` Python SDK (`FastMCP`) with lifespan pattern

## [0.1.0] - 2026-04-26

### Added

- Six-layer architecture: MCP → CLI → Query → Cache → Sync → Parser → Connection
- `TallyConnection`: Async HTTP client with transport-level retries, configurable encoding
- `TallyXMLParser`: Parse ledgers, groups, stock items, vouchers, units, stock groups, cost centers from Tally XML
- `TallyCache`: DuckDB-backed cache with upsert methods, AlterID-based sync state, read-only query enforcement
- `TallySyncEngine`: AlterID-based incremental sync, batched voucher fetching, continuous sync with circuit breaker
- `TallyQuery`: Daily digest, receivables, payables, sales/purchases summary, stock aging, GST summary, cost center summary, search
- `TallyProduct` version detection: Auto-detect Tally.ERP 9 vs TallyPrime via `$$SysInfo:Version`
- MCP Server: Official SDK-based (`FastMCP`) with 12 tool definitions, lifespan pattern, tool annotations
- CLI: Typer-based with init wizard, sync, status, doctor, mcp, config, serve, export, report commands
- Pydantic v2 models for all entities
- Exception hierarchy: `TallyConnectionError`, `TallyDataError`, `TallySyncError`, `TallyBridgeCacheError`
- Config: `pydantic-settings` with env var overrides and configurable encoding
- 285+ tests passing with mock Tally HTTP server
- Docs: `tally-setup.md`, `mcp-setup.md`, `bi-integration.md`
- Recipes: `daily_digest.py`, `overdue_receivables.py`, `gst_mismatch_alert.py`, `anomaly_detector.py`
