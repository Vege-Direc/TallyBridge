"""MCP server using official MCP Python SDK — see RECOMMENDATIONS.md P0-1."""

import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal
from typing import Any, TypeAlias, cast

from loguru import logger  # noqa: F401
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from tallybridge.cache import TallyCache
from tallybridge.config import get_config
from tallybridge.query import TallyQuery

_ANNOTATIONS = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
_WRITE_ANNOTATIONS = ToolAnnotations(readOnlyHint=False, openWorldHint=False)
_Ctx: TypeAlias = Context[Any, Any, Any]

_ALLOWED_SQL_TABLES = frozenset(
    {
        "mst_ledger",
        "mst_group",
        "mst_stock_item",
        "mst_voucher_type",
        "mst_unit",
        "mst_stock_group",
        "mst_cost_center",
        "mst_godown",
        "trn_voucher",
        "trn_ledger_entry",
        "trn_inventory_entry",
        "trn_cost_centre",
        "trn_bill",
        "sync_errors",
        "audit_log",
        "sync_state",
        "schema_version",
    }
)

_DANGEROUS_DUCKDB_FUNCTIONS = frozenset(
    {
        "read_csv_auto",
        "read_csv",
        "read_parquet",
        "read_json",
        "read_json_auto",
        "read_blob",
        "read_text",
        "glob",
        "listdir",
        "fstat",
        "copy",
        "attach",
        "detach",
        "pragma",
    }
)

_MAX_QUERY_LIMIT = 5000
_MAX_SEARCH_LENGTH = 200


def _check_auth(ctx: _Ctx | None) -> None:
    """Validate API key for HTTP transport. No-op for stdio (local trust).

    When mcp_api_key is configured and the server is running in HTTP mode,
    every request must include Authorization: Bearer <key>.
    """
    config = get_config()
    if not config.mcp_api_key:
        return
    transport_mode = os.environ.get("TALLYBRIDGE_MCP_TRANSPORT", "stdio")
    if transport_mode == "stdio":
        return
    if ctx is None:
        raise PermissionError("Authentication required but no context available.")
    request = ctx.request_context
    auth_header: str | None = None
    if hasattr(request, "headers"):
        auth_header = request.headers.get("Authorization", None)
    if not auth_header or not auth_header.startswith("Bearer "):
        raise PermissionError(
            "Authentication required. Set Authorization: Bearer <api_key> header."
        )
    token = auth_header[7:]
    if token != config.mcp_api_key:
        raise PermissionError("Invalid API key.")


def _validate_sql_query(sql: str, limit: int = 1000) -> str:
    """Validate that a SQL string is a safe SELECT query.

    Checks:
    - Must start with SELECT
    - Must not contain dangerous DuckDB functions (file access, etc.)
    - Enforces a row limit
    - Blocks multi-statement queries
    """
    stripped = sql.strip().rstrip(";").strip()
    if not stripped.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed.")
    if ";" in stripped:
        raise ValueError("Multi-statement queries are not allowed.")
    upper_sql = stripped.upper()
    for func in _DANGEROUS_DUCKDB_FUNCTIONS:
        pattern = rf"\b{func}\s*\("
        if re.search(pattern, upper_sql):
            raise ValueError(f"DuckDB function '{func}' is not allowed for security.")
    if "LIMIT" not in upper_sql:
        effective_limit = min(limit, _MAX_QUERY_LIMIT)
        stripped += f" LIMIT {effective_limit}"
    return stripped


@dataclass
class AppContext:
    cache: TallyCache
    query: TallyQuery


@asynccontextmanager
async def app_lifespan(server: FastMCP[Any]) -> Any:
    config = get_config()
    cache = TallyCache(
        config.db_path,
        cache_ttl=float(config.query_cache_ttl),
        slow_threshold=config.slow_query_threshold,
    )
    query = TallyQuery(cache)
    try:
        yield AppContext(cache=cache, query=query)
    finally:
        cache.close()


mcp = FastMCP("TallyBridge", lifespan=app_lifespan, json_response=True)


def _serialize(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, date_type):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if hasattr(obj, "model_dump"):
        return _serialize(obj.model_dump())
    return obj


def _parse_date(value: Any) -> date_type | None:
    if value is None:
        return None
    if isinstance(value, date_type):
        return value
    if isinstance(value, str) and value.strip():
        return date_type.fromisoformat(value.strip())
    return None


def _error_result(message: str) -> CallToolResult:
    return CallToolResult(
        isError=True,
        content=[TextContent(type="text", text=message)],
    )


def _get_app_ctx(ctx: _Ctx) -> AppContext:
    return cast(AppContext, ctx.request_context.lifespan_context)


@mcp.tool(annotations=_ANNOTATIONS)
async def get_tally_digest(
    date: str | None = None, company: str | None = None, ctx: _Ctx | None = None
) -> Any:
    """Complete business summary: sales, purchases, balances, overdue parties."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    d = _parse_date(date)
    return _serialize(app_ctx.query.get_daily_digest(d))


@mcp.tool(annotations=_ANNOTATIONS)
async def get_ledger_balance(
    ledger_name: str,
    date: str | None = None,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """Closing balance of any ledger. Positive=Dr, Negative=Cr."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    try:
        result = app_ctx.query.get_ledger_balance(ledger_name)
        return {"ledger_name": ledger_name, "balance": str(result)}
    except KeyError:
        return _error_result(f"Ledger '{ledger_name}' not found")


@mcp.tool(annotations=_ANNOTATIONS)
async def get_payables(
    overdue_only: bool = False,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """Outstanding purchase invoices — money the business owes."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.query.get_payables(overdue_only=overdue_only)
    )


@mcp.tool(annotations=_ANNOTATIONS)
async def get_receivables(
    overdue_only: bool = False,
    min_days_overdue: int = 0,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """Outstanding sales invoices — money owed to the business."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.query.get_receivables(
            overdue_only=overdue_only, min_days_overdue=min_days_overdue
        )
    )


@mcp.tool(annotations=_ANNOTATIONS)
async def get_party_outstanding(
    party_name: str, company: str | None = None, ctx: _Ctx | None = None
) -> Any:
    """Full receivable/payable position with one party."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(app_ctx.query.get_party_outstanding(party_name))


@mcp.tool(annotations=_ANNOTATIONS)
async def get_sales_summary(
    from_date: str,
    to_date: str,
    group_by: str = "day",
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """Sales by day/week/month/party/item for a date range."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.query.get_sales_summary(
            from_date=_parse_date(from_date) or date_type.today(),
            to_date=_parse_date(to_date) or date_type.today(),
            group_by=group_by,  # type: ignore[arg-type]
        )
    )


@mcp.tool(annotations=_ANNOTATIONS)
async def get_gst_summary(
    from_date: str,
    to_date: str,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """GST collected, ITC, and net liability for a period."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.query.get_gst_summary(
            from_date=_parse_date(from_date) or date_type.today(),
            to_date=_parse_date(to_date) or date_type.today(),
        )
    )


@mcp.tool(annotations=_ANNOTATIONS)
async def search_tally(
    query: str,
    limit: int = 20,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """Search ledgers, parties, voucher narrations."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    if len(query) > _MAX_SEARCH_LENGTH:
        return _error_result(
            f"Search query too long ({len(query)} chars). Max: {_MAX_SEARCH_LENGTH}"
        )
    return _serialize(app_ctx.query.search(query=query, limit=limit))


@mcp.tool(annotations=_ANNOTATIONS)
async def get_sync_status(company: str | None = None, ctx: _Ctx | None = None) -> Any:
    """When data was last synced and record counts."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(app_ctx.cache.get_sync_status())


@mcp.tool(annotations=_ANNOTATIONS)
async def get_low_stock(
    threshold: float = 0,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """Stock items at or below quantity threshold."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    items = app_ctx.query.get_low_stock_items(
        threshold_quantity=Decimal(str(threshold))
    )
    return [
        {"name": i.name, "closing_quantity": str(i.closing_quantity)} for i in items
    ]


@mcp.tool(annotations=_ANNOTATIONS)
async def get_stock_aging(
    date: str | None = None,
    bucket_days: list[int] | None = None,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """How long stock has been sitting — aging by day buckets."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.query.get_stock_aging(
            as_of_date=_parse_date(date), bucket_days=bucket_days
        )
    )


@mcp.tool(annotations=_ANNOTATIONS)
async def get_cost_center_summary(
    from_date: str,
    to_date: str,
    cost_center_name: str | None = None,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """Income and expense breakdown by department or project cost centre."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.query.get_cost_center_summary(
            from_date=_parse_date(from_date) or date_type.today(),
            to_date=_parse_date(to_date) or date_type.today(),
            cost_center_name=cost_center_name,
        )
    )


@mcp.tool(annotations=_ANNOTATIONS)
async def get_balance_sheet(
    to_date: str | None = None,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """Balance sheet grouped by assets and liabilities."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(app_ctx.query.get_balance_sheet(to_date=_parse_date(to_date)))


@mcp.tool(annotations=_ANNOTATIONS)
async def get_profit_loss(
    from_date: str,
    to_date: str,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """Profit & Loss grouped by income and expense for a period."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.query.get_profit_loss(
            from_date=_parse_date(from_date) or date_type.today(),
            to_date=_parse_date(to_date) or date_type.today(),
        )
    )


@mcp.tool(annotations=_ANNOTATIONS)
async def get_ledger_account(
    ledger_name: str,
    from_date: str,
    to_date: str,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """Voucher-level general ledger for a specific ledger and date range."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.query.get_ledger_account(
            ledger_name=ledger_name,
            from_date=_parse_date(from_date) or date_type.today(),
            to_date=_parse_date(to_date) or date_type.today(),
        )
    )


@mcp.tool(annotations=_ANNOTATIONS)
async def get_stock_item_account(
    item_name: str,
    from_date: str,
    to_date: str,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """Quantity movements for a stock item — inward and outward with dates."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.query.get_stock_item_account(
            item_name=item_name,
            from_date=_parse_date(from_date) or date_type.today(),
            to_date=_parse_date(to_date) or date_type.today(),
        )
    )


@mcp.tool(annotations=_ANNOTATIONS)
async def query_tally_data(sql: str, limit: int = 1000, ctx: _Ctx | None = None) -> Any:
    """Run a custom SQL SELECT on the local cache. Tables: mst_ledger, mst_group,
    mst_stock_item, mst_unit, mst_stock_group, mst_cost_center, trn_voucher,
    trn_ledger_entry, trn_inventory_entry, trn_cost_centre, trn_bill.
    Only SELECT queries are allowed. Dangerous functions are blocked."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    try:
        safe_sql = _validate_sql_query(sql, limit)
    except ValueError as exc:
        return _error_result(str(exc))
    return app_ctx.cache.query_readonly(safe_sql)


@mcp.tool(annotations=_ANNOTATIONS)
async def get_sync_errors(
    entity_type: str | None = None,
    limit: int = 100,
    ctx: _Ctx | None = None,
) -> Any:
    """Recent sync errors — failed record GUIDs, entity types, error messages."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.cache.get_sync_errors(entity_type=entity_type, limit=limit)
    )


@mcp.tool(annotations=_ANNOTATIONS)
async def get_gstr1(
    from_date: str,
    to_date: str,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """GSTR-1 outward supply data — invoice-level sales details for GST filing."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.query.get_gstr1(
            from_date=_parse_date(from_date) or date_type.today(),
            to_date=_parse_date(to_date) or date_type.today(),
        )
    )


@mcp.tool(annotations=_ANNOTATIONS)
async def reconcile_itc(
    from_date: str,
    to_date: str,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """ITC reconciliation — compare Tally purchases against GSTR-2A/2B data.

    Matches purchase vouchers by supplier GSTIN + invoice number.
    Returns counts of matched, mismatched, missing-in-Tally, missing-in-2A.
    """
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.query.reconcile_itc(
            from_date=_parse_date(from_date) or date_type.today(),
            to_date=_parse_date(to_date) or date_type.today(),
        )
    )


@mcp.tool(annotations=_ANNOTATIONS)
async def get_gstr9(
    from_date: str,
    to_date: str,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """GSTR-9 annual return data — consolidated yearly GST return sections."""
    _check_auth(ctx)
    from tallybridge.config import get_config as _get_config
    from tallybridge.connection import TallyConnection

    _cfg = _get_config()
    conn = TallyConnection(_cfg)
    try:
        result = await conn.fetch_gstr9(
            from_date=from_date,
            to_date=to_date,
            company=company,
        )
        return _serialize(result)
    finally:
        await conn.close()


@mcp.tool(annotations=_ANNOTATIONS)
async def get_einvoice_status(
    from_date: str,
    to_date: str,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """E-invoice compliance status — IRN coverage and missing invoices."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    try:
        fd = date_type.fromisoformat(from_date)
        td = date_type.fromisoformat(to_date)
    except ValueError:
        return {"error": True, "message": "Invalid date format. Use YYYY-MM-DD."}
    return _serialize(app_ctx.query.get_einvoice_summary(fd, td))


@mcp.tool(annotations=_ANNOTATIONS)
async def get_eway_bill_status(
    from_date: str,
    to_date: str,
    company: str | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """E-Way Bill status — active, expired, and expiring bills."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    try:
        fd = date_type.fromisoformat(from_date)
        td = date_type.fromisoformat(to_date)
    except ValueError:
        return {"error": True, "message": "Invalid date format. Use YYYY-MM-DD."}
    return _serialize(app_ctx.query.get_eway_bill_summary(fd, td))


@mcp.tool(annotations=_ANNOTATIONS)
async def export_data(
    table: str,
    format: str = "csv",
    columns: list[str] | None = None,
    where: str | None = None,
    limit: int | None = None,
    ctx: _Ctx | None = None,
) -> Any:
    """Export cached Tally data as CSV or JSON string. Tables: ledgers, groups,
    stock_items, voucher_types, units, stock_groups, cost_centers, godowns,
    vouchers, ledger_entries, inventory_entries, cost_centre_entries, bill_entries.
    The 'where' parameter only supports simple column=value conditions."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    from tallybridge.export import VALID_TABLES, DataExporter

    if table not in VALID_TABLES:
        return _error_result(
            f"Unknown table '{table}'. Valid: {sorted(VALID_TABLES)}"
        )
    if columns:
        for col in columns:
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", col):
                return _error_result(f"Invalid column name: '{col}'")
    if where:
        _blocked = (
            ";", "--", "/*", "UNION", "DROP", "DELETE",
            "INSERT", "UPDATE", "ALTER", "CREATE", "ATTACH",
        )
        if any(kw in where.upper() for kw in _blocked):
            return _error_result(
                "Invalid WHERE clause. Only simple conditions allowed."
            )
    if limit is not None and (limit < 1 or limit > _MAX_QUERY_LIMIT):
        return _error_result(
            f"Limit must be between 1 and {_MAX_QUERY_LIMIT}."
        )

    exporter = DataExporter(app_ctx.cache)
    if format == "json":
        _, rows = exporter._fetch_data(table, columns, where, limit)
        return _serialize(
            [{k: _serialize(v) for k, v in row.items()} for row in rows]
        )
    csv_str = exporter.export_csv_bytes(table, columns, where, limit)
    return csv_str


@mcp.tool(annotations=_ANNOTATIONS)
async def get_audit_log(
    from_date: str | None = None,
    to_date: str | None = None,
    entity_type: str | None = None,
    operation: str | None = None,
    limit: int = 100,
    ctx: _Ctx | None = None,
) -> Any:
    """Audit log of all write operations (create, cancel, import) with timestamps."""
    _check_auth(ctx)
    app_ctx = _get_app_ctx(ctx)  # type: ignore[arg-type]
    return _serialize(
        app_ctx.query.get_audit_log(
            from_date=_parse_date(from_date),
            to_date=_parse_date(to_date),
            entity_type=entity_type,
            operation=operation,
            limit=limit,
        )
    )


def main() -> None:
    """Entry point for the tallybridge-mcp console script.

    For stdio transport (default, local trust): no authentication needed.
    For HTTP transport (--http flag): requires mcp_api_key to be set.
    Set TALLYBRIDGE_MCP_TRANSPORT=http to enable HTTP mode.
    """
    config = get_config()
    transport_env = os.environ.get("TALLYBRIDGE_MCP_TRANSPORT", "stdio")
    if transport_env == "http":
        if not config.mcp_api_key:
            logger.warning(
                "MCP HTTP transport running without mcp_api_key — "
                "anyone with network access can query your data. "
                "Set TALLYBRIDGE_MCP_API_KEY to secure the endpoint."
            )
    mcp.run(transport=transport_env)  # type: ignore[arg-type]
