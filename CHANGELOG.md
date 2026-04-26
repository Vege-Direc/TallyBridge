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
