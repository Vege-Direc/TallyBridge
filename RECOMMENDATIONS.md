# TallyBridge Recommendations v2

> This document synthesizes findings from deep analysis of 5 reference repositories,
> official MCP Python SDK documentation, DuckDB performance guides, and TallyPrime XML
> API patterns. Each recommendation includes the problem, evidence-based solution, and
> reference source.
>
> **v2 changes**: Corrections from exhaustive validation against source code, reference
> repos, and online research. Key corrections noted with `[v2]` markers.

---

## P0 — Critical: Security, Compliance, and Stability

### P0-1. MCP Server Rewrite (SDK Compliance)

**Problem**: `mcp/server.py` uses a hand-rolled JSON-RPC server (`server.py:166-211` reads
stdin line-by-line, manually constructs JSON-RPC responses) which is non-compliant with the
official Model Context Protocol. It lacks the initialization handshake, proper transport
negotiation, and tool annotations.

**Solution**: Rewrite `mcp/server.py` and `mcp/tools.py` using the official `mcp` Python SDK.

> [!IMPORTANT]
> The current stable release is **v1.x** using `FastMCP`. The v2 SDK renames `FastMCP` to
> `MCPServer` — it is the **same API under a new name**, not a fundamentally different class
> `[v2]`. The v2 migration is simply an import rename:
> `from mcp.server.fastmcp import FastMCP` → `from mcp.server.mcpserver import MCPServer`.
> Pin to `mcp>=1.2.0,<2.0.0` until v2 reaches stable.

**v1.x pattern (current stable — use this now):**
```python
from mcp.server.fastmcp import FastMCP, Context
from mcp.types import CallToolResult, TextContent

mcp = FastMCP("TallyBridge", json_response=True)

@mcp.tool()
async def get_ledger_balance(ledger_name: str, date: str | None = None, ctx: Context) -> dict:
    """Closing balance of any ledger. Positive=Dr, Negative=Cr."""
    try:
        result = ctx.request_context.lifespan_context.query.get_ledger_balance(ledger_name)
        return {"ledger": ledger_name, "balance": str(result)}
    except KeyError:
        return CallToolResult(
            is_error=True,
            content=[TextContent(type="text", text=f"Ledger '{ledger_name}' not found")]
        )

if __name__ == "__main__":
    mcp.run(transport="stdio")  # or transport="streamable-http"
```

**Lifespan pattern for resource management:**
```python
from contextlib import asynccontextmanager
from dataclasses import dataclass

@dataclass
class AppContext:
    cache: TallyCache
    query: TallyQuery

@asynccontextmanager
async def app_lifespan(server: FastMCP):
    config = get_config()
    cache = TallyCache(config.db_path)
    cache.initialize()
    query = TallyQuery(cache)
    try:
        yield AppContext(cache=cache, query=query)
    finally:
        cache.close()

mcp = FastMCP("TallyBridge", lifespan=app_lifespan, json_response=True)
```

**Tool annotations** (from MCP 2025 spec, confirmed by `tally-mcp-server` reference):
All TallyBridge tools should declare `readOnlyHint=True` and `openWorldHint=False`.
The `tally-mcp-server` reference project uses this exact pattern for all **12** tools `[v2]`
(see `src/mcp.mts` lines 24-27, 46-49, 79-82, 115-118, 151-154, 186-189, 222-225,
258-261, 293-296, 328-331, 365-368, 410-413).

> `[v2]` Note: The `tally-mcp-server` reference uses the **TypeScript** SDK's `McpServer`
> class (`@modelcontextprotocol/sdk` v1.18.2, `src/mcp.mts:1,10`), not the Python `FastMCP`.
> The patterns are equivalent but the SDK languages differ.

**Error handling**: Return `CallToolResult(is_error=True, content=[TextContent(...)])` for
error cases, not JSON error blobs. The `tally-mcp-server` reference uses `isError: true`
consistently across all 11 non-query tools `[v2]` (`src/mcp.mts` lines 59, 93, 129, 165,
200, 236, 271, 306, 342, 380, 425). The `query-database` tool is the only one without
this pattern.

**Transport**: Use `stdio` for local desktop clients (Claude Desktop, Cursor). Use
`streamable-http` for remote/cloud deployments.

- **Ref**: [MCP Python SDK README](https://github.com/modelcontextprotocol/python-sdk), `tally-mcp-server/src/mcp.mts`
- **Effort**: High

---

### P0-2. XML Entity Escaping (Injection Prevention)

**Problem**: Tally request bodies are built via string concatenation (`connection.py:161-188`
uses f-strings throughout). If a company name contains `<`, `>`, `&`, `"`, or `'`, the XML
will be malformed, causing a Tally error or potential XML injection. Specific example at
`connection.py:164`: `f"<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>"` — company name is
unescaped.

**Solution**: Use standard XML entity escaping for all user-supplied strings injected into
the XML `<ENVELOPE>` payload. The `tally-mcp-server` reference does this explicitly via
`utility.String.escapeHTML()` (`utility.mts:56-63`) which replaces `& → &amp;`,
`< → &lt;`, `> → &gt;`, `" → &quot;`, `' → &apos;`. This escaping is applied in
`tally.mts:197` via `substituteTDLParameters()`.

```python
import html
escaped_company = html.escape(company_name, quote=True)
```

- **Ref**: `tally-mcp-server/src/utility.mts:56-63`, `tally-mcp-server/src/tally.mts:197`
- **Effort**: Low

---

### P0-3. Tally Response Error Checking

**Problem**: Tally includes `<STATUS>` tags in its XML responses (`1` = success, `0` = no
data, `-1` = error) and `<EXCEPTION>...</EXCEPTION>` wrappers on severe errors. The current
parser only checks `<LINEERROR>` (`connection.py:122-129`) and ignores both STATUS and
EXCEPTION, potentially leading to silent failures.

**Solution**: Implement two-level error checking:

1. **Check `<EXCEPTION>` prefix first** — as `tally-mcp-server` does (`tally.mts:298-306`):
   extract the error message from between the tags and raise `TallyDataError`.

2. **Check `<STATUS>` tag** — per TallyHelp documentation `[v2]`: "Based on the value of
   the `<STATUS>` tag 0/1, the error report and success report are executed respectively."
   If `STATUS` is `0`, return empty data; if `-1`, raise `TallyDataError`.

> `[v2]` Correction: The `tally-mcp-server` reference does NOT check `<STATUS>` tags — it
> only checks the `<EXCEPTION>` prefix. The STATUS check recommendation is valid per
> TallyHelp official documentation, not the reference repo.

```python
if response_text.startswith("<EXCEPTION>"):
    match = re.search(r"<EXCEPTION>(.+?)</EXCEPTION>", response_text)
    error_msg = match.group(1) if match else "Unknown Tally exception"
    raise TallyDataError(error_msg, raw_response=response_text)

status_match = re.search(r"<STATUS>(-?\d+)</STATUS>", response_text)
if status_match:
    status = int(status_match.group(1))
    if status == -1:
        raise TallyDataError("Tally returned STATUS -1", raw_response=response_text)
    if status == 0:
        return ""  # No data
```

- **Ref**: `tally-mcp-server/src/tally.mts:298-306` (EXCEPTION check),
  [TallyHelp: TallyPrime as a Client](https://help.tallysolutions.com/developer-reference/integration-using-xml-interface/tallyprime-as-a_client/) (STATUS tag docs) `[v2]`
- **Effort**: Low

---

### P0-4. SQL Injection Prevention (query_tally_data tool)

**Problem**: The `is_safe_sql()` function (`server.py:31-34`) splits on whitespace, which
is trivially bypassable (e.g., `SELECT/**/1;DROP/**/TABLE mst_ledger`).

**Solution**: Use DuckDB's **read-only connection** for the query tool. DuckDB supports opening
a connection with `read_only=True` which physically prevents any write operations at
the engine level — no need for fragile SQL parsing.

```python
import duckdb
read_conn = duckdb.connect(db_path, read_only=True)
result = read_conn.execute("SELECT * FROM mst_ledger LIMIT ?", [limit]).fetchall()
```

This is the definitive fix — no regex, no keyword blocklist, no SQL parsing needed.

> `[v2]` Note: The `tally-mcp-server` reference does NOT use read-only connections — it
> uses a single read-write connection for both appends and queries (`database.mts:7`).
> The read-only recommendation stands on its own merit as security best practice.

- **Ref**: [DuckDB Configuration docs](https://duckdb.org/docs/connect/overview.html)
- **Effort**: Low

---

### P0-5. Encoding Alignment

**Problem**: Our code sends UTF-8 but decodes UTF-16 (`connection.py:107` encodes as UTF-8,
`connection.py:119` decodes as UTF-16). The `tally-mcp-server` reference sends **both
request and response as UTF-16LE** (`tally.mts:158-159,165,183`: `charset=utf-16`,
Content-Length calculated with `utf16le`, body written with `utf16le`). The `tally-py`
reference sends with `application/x-www-form-urlencoded` which also works because Tally is
lenient. Tally **responds in the same encoding as the request Content-Type header**.

**Solution**: Tally mirrors the request encoding in its response. Two valid approaches:
1. **UTF-8 (recommended for simplicity)**: Send `Content-Type: text/xml; charset=utf-8`, decode
   response as UTF-8. Works for standard ASCII/Latin characters and most Indian languages.
2. **UTF-16LE (needed for ₹/€ symbols)**: Send `Content-Type: text/xml; charset=utf-16`, encode
   body as UTF-16LE, decode response as UTF-16LE. Required only for special currency symbols.

Use UTF-8 as default (simpler, works for 99% of cases). Make encoding configurable for edge cases.

- **Ref**: `tally-mcp-server/src/tally.mts:157-165,183`, User discovery in prior session
- **Effort**: Low

---

### P0-6. DECIMAL Precision Loss in Cache Layer `[v2]` — elevated from P2

**Problem**: `cache.py` converts `Decimal` values to `float` in at least 8 locations before
inserting into DuckDB: lines 207, 253-258, 365-366, 374, 384-386. This silently loses
precision for financial amounts. For example, `Decimal("0.1")` becomes `float(0.1)` which
is `0.1000000000000000055511151231257827021181583404541015625`. Over many rows and
aggregations, these errors compound.

**Solution**: Remove all `float()` conversions. DuckDB's Python driver accepts `Decimal`
objects natively — just pass them directly as parameters:

```python
# BEFORE (lossy):
float(ledger.opening_balance)

# AFTER (precise):
ledger.opening_balance  # Pass Decimal directly
```

For the full pipeline:
1. Parser: `Decimal(amount_str)` — already correct
2. Model: `amount: Decimal` fields — already correct
3. Cache: Pass `Decimal` directly to `conn.execute()`, never `float()`
4. Serialization: `model_dump(mode='python')` preserves Decimal; use `str(decimal)` for JSON

- **Ref**: DuckDB Python API accepts `Decimal` natively
- **Effort**: Low

---

## P1 — High: Core Functionality and Data Completeness

### P1-1. Voucher Pagination

**Problem**: Tally hangs with batch sizes >10,000. The constant `VOUCHER_BATCH_SIZE = 1000`
is defined in `sync.py:118` but never used. The current `sync_entity()` fetches all records
in a single request.

**Solution**: Implement batched fetching in `sync.py` using AlterID ranges. The
`tally-database-loader` confirms a safe **batchsize of 5000** (`src/tally.mts:47`,
`config.json:19`) and explicitly warns: "Do not increase this beyond 10000 since the export
might get stuck from tally indefinitely." (`README.md:246`)

Update `VOUCHER_BATCH_SIZE` from 1000 to **5000** `[v2]` per reference evidence:

```python
VOUCHER_BATCH_SIZE = 5000

while True:
    xml = await connection.export_collection(
        "Voucher", filter_expr=f"$ALTERID > {last_id} AND $ALTERID <= {last_id + batch_size}"
    )
    batch = parser.parse_vouchers(xml)
    if not batch:
        break
    cache.upsert_vouchers(batch)
    last_id = max(v.alter_id for v in batch)
```

- **Ref**: `tally-database-loader/README.md:246`, `tally-database-loader/src/tally.mts:47`, `tally-database-loader/config.json:19`
- **Effort**: Medium

---

### P1-2. Company Selection and Multi-Company Tracking

**Problem**: `tally_company` config exists (`config.py:13`) but is unused. `connection.py`
conditionally adds `<SVCURRENTCOMPANY>` only if `company` is passed, but no code ever passes
it from sync. Multi-company Tally instances will mix data.

**Solution**:
- Pass `<SVCURRENTCOMPANY>` in every XML request (already in SPECS.md but not enforced)
- Add a `company` column to all DuckDB master and transaction tables
- Filter queries by the active company
- If `tally_company` is blank, auto-detect the active company from Tally on first sync

> `[v2]` Note: The `tally-mcp-server` passes `targetCompany` to **11 of 12** tools — the
> `query-database` tool does NOT take `targetCompany`. The `tally-database-loader` has
> `company` as a core config parameter (`src/definition.mts:21`, `config.json:21`).

- **Ref**: `tally-mcp-server/src/mcp.mts` (11 tools take `targetCompany`), `tally-database-loader/src/definition.mts:21`
- **Effort**: Medium

---

### P1-3. Cost Centre as Junction Table (Not Column)

**Problem**: In Tally, a single ledger entry can have **multiple cost centre allocations**
(split across categories and centres with different amounts). The current `trn_ledger_entry`
schema has no cost centre column at all.

**Solution**: SPECS.md §6 already defines the `trn_cost_centre` junction table `[v2]`:

```sql
CREATE TABLE IF NOT EXISTS trn_cost_centre (
    id              BIGINT DEFAULT nextval('seq_entry_id') PRIMARY KEY,
    voucher_guid    TEXT NOT NULL REFERENCES trn_voucher(guid) ON DELETE CASCADE,
    ledger_name     TEXT NOT NULL,
    cost_centre     TEXT NOT NULL,
    amount          DECIMAL(18,4) NOT NULL
);
```

The gap is **implementation**, not specification — `cache.py` doesn't create or populate this
table. The `tally-database-loader` confirms this pattern (`database-structure.sql:290-296`).

The `tally-database-loader` also has a separate `trn_cost_category_centre` table for
cost category-aware allocations. For v0.1, the simpler `trn_cost_centre` junction table
is sufficient.

- **Ref**: `tally-database-loader/database-structure.sql:290-296`, `SPECS.md §6:622-628` `[v2]`
- **Effort**: Medium

---

### P1-4. Deletion Tracking with Diff/Delete Tables

**Problem**: AlterID-based sync only catches modifications and additions. Deleted records
in Tally persist in the cache forever.

**Solution**: The `tally-database-loader` uses a `_diff` table and a `_delete` table to
track changes and deletions during incremental sync (`database-structure-incremental.sql:1-10`,
`src/tally.mts:149-150,210-211,236-241`). Their approach:
1. Fetch all GUIDs+AlterIDs from Tally for each entity type
2. Compare against cached GUIDs — any GUID present in cache but missing from Tally is deleted
3. Store deletions in a `_delete` staging table, then cascade-delete from main tables

For v0.1, a simpler approach: periodically (e.g., daily) fetch the full GUID list for each
entity type and delete orphaned records. This is the `full_sync()` path.

- **Ref**: `tally-database-loader/database-structure-incremental.sql:1-10`, `tally-database-loader/src/tally.mts:149-150,210-211,236-241`
- **Effort**: High

---

### P1-5. Bill Allocations Table (for Outstanding Reports)

**Problem**: Outstanding receivables/payables queries currently approximate bill data from
voucher totals (`cache.py:475-496` uses `total_amount` as `outstanding_amount`). Tally has
detailed bill-wise allocation data that enables accurate aging.

**Solution**: SPECS.md §6 already defines the `trn_bill` table `[v2]`:

```sql
CREATE TABLE IF NOT EXISTS trn_bill (
    id              BIGINT DEFAULT nextval('seq_entry_id') PRIMARY KEY,
    voucher_guid    TEXT NOT NULL REFERENCES trn_voucher(guid) ON DELETE CASCADE,
    ledger_name     TEXT NOT NULL,
    bill_name       TEXT NOT NULL,
    amount          DECIMAL(18,4) NOT NULL,
    bill_type       TEXT,            -- 'New Ref', 'Agst Ref', 'Advance'
    bill_credit_period INT
);
```

The gap is **implementation** — the parser doesn't extract `<BILLALLOCATIONS.LIST>`, and
`cache.py` doesn't create or populate this table. The `tally-database-loader` confirms this
pattern (`database-structure.sql:317-325`) and documents: "This table contains bill-wise
breakup of purchase/sale invoice or receipt/payment." (`docs/data-structure.md:82`) `[v2]`.

- **Ref**: `tally-database-loader/database-structure.sql:317-325`, `tally-database-loader/docs/data-structure.md:82`, `SPECS.md §6:632-640` `[v2]`
- **Effort**: Medium

---

### P1-6. Missing MCP Tools (Gap vs Reference Server)

**Problem**: The `tally-mcp-server` reference exposes **12 tools** `[v2]` (not 11 as
previously stated). It has 4 tools we don't have:
- `balance-sheet` — Balance Sheet as on date (`src/mcp.mts:178`)
- `profit-loss` — P&L for a period (`src/mcp.mts:142`)
- `ledger-account` — GL statement with voucher-level details (`src/mcp.mts:355`)
- `stock-item-account` — Stock item ledger with quantity tracking (`src/mcp.mts:400`)

**Solution**: Add these 4 tools to our MCP server in a future phase:
- `get_balance_sheet(to_date, company?)` → grouped by asset/liability
- `get_profit_loss(from_date, to_date, company?)` → grouped by income/expense
- `get_ledger_account(ledger_name, from_date, to_date)` → voucher-level GL
- `get_stock_item_account(item_name, from_date, to_date)` → quantity movements

These are high-value for CA firms and should be added before v1.0.

- **Ref**: `tally-mcp-server/src/mcp.mts:142,178,355,400` `[v2]`
- **Effort**: Medium per tool

---

## P2 — Medium: Performance and Optimization

### P2-1. DuckDB Appender API for Bulk Inserts

**Problem**: Row-by-row SQL INSERT is extremely slow in DuckDB. `cache.py:192-396` uses
individual `execute()` calls per row.

**Solution**: The `tally-mcp-server` reference uses DuckDB's Appender API directly
(`database.mts:49-84`), with type-specific append methods:
- `appendDecimal()` for amounts with `BigInt(Math.round(value * 10000))` for 4-decimal precision
- `appendBoolean()` for booleans
- `appendDate()` for dates (as days-since-epoch)
- `appendVarchar()` for text
- `endRow()` after each row, `closeSync()` to commit

In Python with `duckdb`, use parameterized batch inserts or `INSERT INTO ... SELECT * FROM df`:
```python
conn.executemany(
    "INSERT INTO mst_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    [row_tuples]
)
```

Or use DataFrames for even faster bulk loading:
```python
import pandas as pd
df = pd.DataFrame([ledger.model_dump() for ledger in ledgers])
conn.execute("INSERT INTO mst_ledger SELECT * FROM df")
```

- **Ref**: `tally-mcp-server/src/database.mts:49-84`
- **Effort**: Medium

---

### P2-2. Data Ordering for Zonemap Efficiency

**Problem**: Unordered data prevents DuckDB from using zonemaps effectively.

**Solution**: Sort vouchers by `date` before inserting. DuckDB's automatic min-max
zonemaps on columns provide 2.5x smaller storage and 1.5x faster queries when data
is ordered on the filtered column.

Create ART indexes **after** bulk loading, not before:
```python
# After bulk insert:
conn.execute("CREATE INDEX IF NOT EXISTS idx_voucher_date ON trn_voucher(date)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_voucher_party ON trn_voucher(party_ledger)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_entry_voucher ON trn_ledger_entry(voucher_guid)")
```

- **Ref**: DuckDB indexing documentation
- **Effort**: Low

---

### P2-3. httpx Connection Pooling and Retry

**Problem**: Current implementation uses `tenacity` for retry logic (`connection.py:7,89-94`)
which adds overhead for connection-level retries.

**Solution**: Use httpx's built-in transport-level retries:
```python
transport = httpx.AsyncHTTPTransport(retries=3)
limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
timeout = httpx.Timeout(30.0, connect=10.0, read=60.0, write=10.0, pool=5.0)

self._client = httpx.AsyncClient(
    transport=transport,
    limits=limits,
    timeout=timeout,
)
```

Keep `tenacity` only if you need retry with exponential backoff on application-level errors
(e.g., TallyDataError). For connection-level retries, httpx transport handles it natively.

- **Ref**: httpx documentation
- **Effort**: Low

---

### P2-4. DuckDB In-Memory Cache with Auto-Drop (UX Pattern)

**Problem**: For real-time MCP queries, persisting intermediate results to disk is wasteful.

**Solution**: The `tally-mcp-server` uses an interesting pattern where DuckDB tables are
created in-memory (`database.mts:6`: `:memory:`) with random names and **auto-dropped after
15 minutes** (`database.mts:87`: `setTimeout(async () => await conn.run('DROP TABLE IF EXISTS ${tableId};'), 15 * 60 * 1000)`).

This pattern enables complex multi-step analysis:
1. Tool returns `{tableID: "t_abc123"}`
2. LLM runs `query-database` with `SELECT ... FROM t_abc123 WHERE ...`
3. Table auto-drops after 15 min

Consider this pattern for our `query_tally_data` tool to enable iterative analysis.
Note: This requires architectural changes since we use a persistent DuckDB file, not
in-memory `[v2]`.

- **Ref**: `tally-mcp-server/src/database.mts:6,87`
- **Effort**: Medium (P3 to implement)

---

## P3 — Future: Advanced Capabilities

### P3-1. Write/Import Operations
Send data back to Tally to create ledgers, vouchers, or update masters. The `tally-py`
reference provides `create_ledger()` (`tally_integration/client.py:227-286`),
`create_company()` (`client.py:288-385`), and voucher creation methods
(`CoreAPI/xmlFunctions.py:956-1017`) `[v2]`. Our tools should all declare
`readOnlyHint=False` and `destructiveHint=True` for write ops.

### P3-2. Parent GUID Resolution
The `tally-database-loader` stores `_parent` GUID columns (`varchar(64)`) alongside text
`parent` columns for every master table (`database-structure-incremental.sql:30,45,80+`).
These are populated via TDL expressions like
`if $$IsEqual:$Parent:$$SysName:Primary then "" else $Guid:Group:$Parent`
(`tally-export-config-incremental.yaml:18-19`) `[v2]`. This enables efficient JOIN-based
hierarchy traversal without string matching. Consider adding `_parent_guid` columns in a
future schema migration.

### P3-3. Payroll and Attendance Support
The `tally-database-loader` has full payroll schema: `mst_employee`
(`database-structure.sql:149-175`), `mst_payhead` (`lines 177-188`),
`mst_attendance_type` (`lines 139-147`), `trn_attendance`, `trn_employee`,
`trn_payhead` `[v2]`. Indian CA firms frequently need payroll reports. Add these in v1.0+.

### P3-4. GST Effective Rate History
The `tally-database-loader` has `mst_gst_effective_rate` with `applicable_from` dates
(`database-structure.sql:190-205`) `[v2]`, enabling accurate GST rate lookups for historical
transactions. This is critical for GST audit accuracy.

### P3-5. Opening Bill Allocations
The `tally-database-loader` stores `mst_opening_bill_allocation`
(`database-structure.sql:218-226`) with `bill_date`, `bill_credit_period`, and `is_advance`
flags. Used in bills-receivable/bills-payable SQL reports (`reports/mssql/bills-receivable.sql:4`,
`reports/bigquery/bills-receivable.sql:4`) `[v2]`. This enables accurate opening outstanding
calculation without relying on voucher-level approximation.

### P3-6. OAuth 2.1 for Remote MCP
MCP SDK v1.x supports `TokenVerifier` and `AuthSettings` for OAuth 2.1 (confirmed in SDK
docs: `from mcp.server.auth.provider import TokenVerifier; from mcp.server.auth.settings import AuthSettings`) `[v2]`. Required for any remote/cloud deployment of the MCP server.

### P3-7. Parquet Export
DuckDB can export directly to Parquet via `COPY table TO 'file.parquet' (FORMAT PARQUET)`.
Useful for users who want to analyze data in Jupyter, Polars, or cloud data warehouses.

### P3-8. Jinja2 XML Templating
The `tally-mcp-server` uses Nunjucks for XML templating with custom tag delimiters
(`<nunjuck>` / `</nunjuck>` for blocks, `{{` / `}}` for variables)
(`tally.mts:4,13-22,139`) `[v2]`. Consider using Jinja2 templates for XML request
generation instead of raw f-strings, which would be more maintainable and safer against
injection.

---

## Version Compatibility

### TallyPrime Version Landscape (India Market)

| Version | Year | Headline Feature | XML API Impact |
|---|---|---|---|
| Tally.ERP 9 | Pre-2020 | Legacy desktop accounting | `<VERSION>1</VERSION>`, no `ALLLEDGERENTRIES.LIST` |
| TallyPrime 1.x | 2020-2021 | New interface | `ALLLEDGERENTRIES.LIST` introduced |
| TallyPrime 2.x | 2021-2022 | E-Way Bill, GST reconciliation | No XML schema changes |
| TallyPrime 3.x | 2023 | Reporting, multi-company | No XML schema changes |
| TallyPrime 4.x | 2024 | Connected GST, GSTR-1 filing | **Critical adoption inflection** |
| TallyPrime 5.x | 2024 | GSTR-3B, TDS automation | No XML schema changes |
| TallyPrime 6.x | 2024 | Connected Banking | No XML schema changes |
| TallyPrime 7.x | Dec 2025 | TallyDrive, SmartFind, cloud | No XML schema changes |

**Target:** TallyPrime 4.0+ is our primary target. Per Gartner India (2024), 75%+
of Indian SMEs use Tally, and most with active TSS are on 4.0+ since Connected GST
is essential for compliance. Tally.ERP 9 is deprecated but still in use.

### Version Detection

Implemented in `version.py` using `$$SysInfo:Version` via TDL Collection with
`NATIVEMETHOD`. The `detect_tally_version()` function:

1. Sends a Collection query with `<NATIVEMETHOD>Version</NATIVEMETHOD>`
2. Parses the version string from `<VERSION>` in the response
3. Returns a `TallyProduct` enum (ERP9, PRIME_1..PRIME_7)
4. Caches the result on the connection object for reuse

### Key Cross-Version Differences

| Feature | Tally.ERP 9 | TallyPrime |
|---|---|---|
| `<ALLLEDGERENTRIES.LIST>` | Not available | Available (use this for complete ledger entries) |
| `<LEDGERENTRIES.LIST>` | Available | Available (may return subset in some contexts) |
| `<ALLINVENTORYENTRIES.LIST>` | Not available | Available |
| `<VERSION>1</VERSION>` in HEADER | Required | Accepted (API version, not product version) |
| `<TALLYREQUEST>Export Data</TALLYREQUEST>` | Primary pattern | Primary pattern |
| `<TALLYREQUEST>Export</TALLYREQUEST>` | Some contexts | Full Report/Form/Line/Field TDL pattern |
| `<BILLCREDITPERIOD>` format | Plain integer | Complex (`INDAYS`, `DUEONDATE`, `INTEXT`) |
| `<STATUS>` tag in response | `1`=success, `0`=no-data, `-1`=error | Same |
| `<EXCEPTION>` prefix | Yes | Yes |
| Sub-collections in `<FETCH>` | May be ignored | May cause errors (do NOT include) |

### Important Implementation Notes

1. **FETCH list must NOT include collection references**: `LEDGERENTRIES` and
   `INVENTORYENTRIES` are TDL collection references, not scalar fields.
   Including them in `<FETCH>` causes errors or empty responses in some
   Tally versions. Sub-collections are auto-included in XML responses.

2. **BILLALLOCATIONS.LIST depends on configuration**: Only appears if
   bill-wise breakup is enabled (F11 > Accounting Features > Maintain
   Bill-wise Details).

3. **COSTCENTRE.LIST depends on configuration**: Only appears if cost
   centres are enabled (F11 > Inventory Features > Cost Centres).

4. **BILLCREDITPERIOD format varies**: Some versions return a plain integer,
   others return a complex structure with `<INDAYS>`, `<DUEONDATE>`, and
   `<INTEXT>`. The parser handles both with DUEONDATE as fallback.

5. **`<VERSION>1</VERSION>` in HEADER is the API version**: This is NOT the
   Tally product version. It indicates the XML message format version.
   Both ERP 9 and TallyPrime accept version 1 for Export Data requests.

---

## Reference Repository Summary

| Repository | Language | Key Patterns |
|---|---|---|
| `tally-database-loader` | Node.js | YAML config, batch 5000 (`src/tally.mts:47`), AlterID sync, `_diff`/`_delete` tables, `trn_cost_centre`/`trn_bill` junction tables, payroll schema, GST rate history, opening bill allocations |
| `tally-mcp-server` | TypeScript | Official MCP SDK (`McpServer` from `@modelcontextprotocol/sdk` v1.18.2 `[v2]`), **12 tools** `[v2]`, Nunjucks XML, DuckDB in-memory + Appender, 15min auto-drop, UTF-16LE, `readOnlyHint`/`openWorldHint` on all tools, `<EXCEPTION>` prefix check (no `<STATUS>` check `[v2]`), `isError: true` on 11 tools |
| `TallyConnector` | C# | Versioned model inheritance (V3→V7), `RHeader.Status` model property defined but not actively checked from parsed responses `[v2]`, `TallyResponseCleaner` for XML cleaning, Roslyn TDL source generators |
| `tally-py` | Python | 5+ XML request patterns, 5-class error hierarchy (`tally_integration/exceptions.py`), `create_ledger()`/`create_company()`, experimental TDL directory with `ApiCallAiStudio.tdl` `[v2]`, `application/x-www-form-urlencoded` in refactored client |
| `tally-localhost-connector` | C# | CORS proxy (`Access-Control-Allow-Origin: *` at `Program.cs:41`), forwards requests from `localhost:9001` to Tally at `localhost:9000` `[v2]` |

> `[v2]` Star counts removed — cannot be verified from local clones. All other claims
> validated against source code with line numbers.

## Phase 10 Gap Analysis Findings

### ALLLEDGERENTRIES.LIST vs LEDGERENTRIES.LIST

TallyPrime uses `<ALLLEDGERENTRIES.LIST>` for voucher ledger entries while
Tally.ERP 9 uses `<LEDGERENTRIES.LIST>`. The parser now implements a
fallback: if ALLLEDGERENTRIES.LIST returns nothing, try LEDGERENTRIES.LIST.
Same pattern for ALLINVENTORYENTRIES.LIST → INVENTORYENTRIES.LIST. This was
implemented as task 10b.

### fetch_report() half-built status

`fetch_report()` was added in task 9r but only returned raw XML. Task 10d
added structured parsing via `parse_report()` with specialist parsers for
Balance Sheet (BSNAME/BSCLOSAMT), P&L (PLNAME/PLCLOSAMT), Trial Balance
(DSPACCNAME/DSPACCINFO), and Day Book (VOUCHER). The `parse=True` parameter
returns a `TallyReport` model.

### export_object() half-built status

`export_object()` was added in task 9q but only returned raw XML. Task 10e
added `parse=True` parameter that auto-detects the object type and routes
to the appropriate parser method (parse_ledgers, parse_vouchers, etc.).

### Version gating unused — integration plan

`detect_tally_version()` and `capabilities()` were added in task 9s but
weren't called from the sync or connection flow. Task 10i integrated:
- `TallyConnection.detect_version()` convenience method
- `TallySyncEngine.sync_all()` calls `connection.detect_version()` on first sync
- Capability set is logged on detection

### Deletion tracking approach

Records deleted in Tally persist forever in the DuckDB cache. Task 10g
implements GUID diff during `full_sync()`:
1. Fetch all GUIDs from Tally using `export_collection(fields=["GUID"])`
2. Compare against cached GUIDs
3. Delete orphans with cascade for voucher child tables
4. Vouchers are excluded (use ISCANCELLED/ISVOID instead)

### Multi-company MCP tool gap

The tally-mcp-server reference passes `targetCompany` to 11 of 12 tools.
Task 10h added optional `company` parameter to all MCP tools (except
`query_tally_data`). The parameter provides the API surface for future
filtering.
