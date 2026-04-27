"""MCP server using official MCP Python SDK — see RECOMMENDATIONS.md P0-1."""

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from loguru import logger  # noqa: F401
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, TextContent

from tallybridge.cache import TallyCache
from tallybridge.config import get_config
from tallybridge.query import TallyQuery


def _check_auth(ctx: Context) -> None:
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
    request = ctx.request_context
    auth_header = None
    if hasattr(request, "headers"):
        auth_header = request.headers.get("Authorization", None)
    if not auth_header or not auth_header.startswith("Bearer "):
        raise PermissionError(
            "Authentication required. Set Authorization: Bearer <api_key> header."
        )
    token = auth_header[7:]
    if token != config.mcp_api_key:
        raise PermissionError("Invalid API key.")


@dataclass
class AppContext:
    cache: TallyCache
    query: TallyQuery


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    config = get_config()
    cache = TallyCache(config.db_path)
    query = TallyQuery(cache)
    try:
        yield AppContext(cache=cache, query=query)
    finally:
        cache.close()


mcp = FastMCP("TallyBridge", lifespan=app_lifespan, json_response=True)


def _serialize(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if hasattr(obj, "model_dump"):
        return _serialize(obj.model_dump())
    return obj


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        return date.fromisoformat(value.strip())
    return None


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def get_tally_digest(date: str | None = None, ctx: Context = None) -> dict:
    """Complete business summary: sales, purchases, balances, overdue parties."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    d = _parse_date(date)
    return _serialize(app_ctx.query.get_daily_digest(d))


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def get_ledger_balance(
    ledger_name: str, date: str | None = None, ctx: Context = None
) -> dict:
    """Closing balance of any ledger. Positive=Dr, Negative=Cr."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    try:
        result = app_ctx.query.get_ledger_balance(ledger_name)
        return {"ledger_name": ledger_name, "balance": str(result)}
    except KeyError:
        return CallToolResult(
            is_error=True,
            content=[
                TextContent(
                    type="text",
                    text=f"Ledger '{ledger_name}' not found",
                )
            ],
        )


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def get_receivables(
    overdue_only: bool = False, min_days_overdue: int = 0, ctx: Context = None
) -> list:
    """Outstanding sales invoices — money owed to the business."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return _serialize(
        app_ctx.query.get_receivables(
            overdue_only=overdue_only, min_days_overdue=min_days_overdue
        )
    )


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def get_party_outstanding(party_name: str, ctx: Context = None) -> dict:
    """Full receivable/payable position with one party."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return _serialize(app_ctx.query.get_party_outstanding(party_name))


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def get_sales_summary(
    from_date: str, to_date: str, group_by: str = "day", ctx: Context = None
) -> list:
    """Sales by day/week/month/party/item for a date range."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return _serialize(
        app_ctx.query.get_sales_summary(
            from_date=_parse_date(from_date) or date.today(),
            to_date=_parse_date(to_date) or date.today(),
            group_by=group_by,
        )
    )


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def get_gst_summary(from_date: str, to_date: str, ctx: Context = None) -> dict:
    """GST collected, ITC, and net liability for a period."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return _serialize(
        app_ctx.query.get_gst_summary(
            from_date=_parse_date(from_date) or date.today(),
            to_date=_parse_date(to_date) or date.today(),
        )
    )


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def search_tally(query: str, limit: int = 20, ctx: Context = None) -> dict:
    """Search ledgers, parties, voucher narrations."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return _serialize(app_ctx.query.search(query=query, limit=limit))


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def get_sync_status(ctx: Context = None) -> dict:
    """When data was last synced and record counts."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return _serialize(app_ctx.cache.get_sync_status())


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def get_low_stock(threshold: float = 0, ctx: Context = None) -> list:
    """Stock items at or below quantity threshold."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    items = app_ctx.query.get_low_stock_items(
        threshold_quantity=Decimal(str(threshold))
    )
    return [
        {"name": i.name, "closing_quantity": str(i.closing_quantity)} for i in items
    ]


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def get_stock_aging(
    date: str | None = None, bucket_days: list[int] | None = None, ctx: Context = None
) -> list:
    """How long stock has been sitting — aging by day buckets."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return _serialize(
        app_ctx.query.get_stock_aging(
            as_of_date=_parse_date(date), bucket_days=bucket_days
        )
    )


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def get_cost_center_summary(
    from_date: str,
    to_date: str,
    cost_center_name: str | None = None,
    ctx: Context = None,
) -> list:
    """Income and expense breakdown by department or project cost centre."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return _serialize(
        app_ctx.query.get_cost_center_summary(
            from_date=_parse_date(from_date) or date.today(),
            to_date=_parse_date(to_date) or date.today(),
            cost_center_name=cost_center_name,
        )
    )


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def query_tally_data(sql: str, limit: int = 1000, ctx: Context = None) -> list:
    """Run a custom SQL SELECT on the local cache. Tables: mst_ledger, mst_group,
    mst_stock_item, mst_unit, mst_stock_group, mst_cost_center, trn_voucher,
    trn_ledger_entry, trn_inventory_entry, trn_cost_centre, trn_bill."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    if "LIMIT" not in sql.upper():
        sql = sql + f" LIMIT {limit}"
    return app_ctx.cache.query_readonly(sql)


@mcp.tool(
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
async def get_sync_errors(
    entity_type: str | None = None, limit: int = 100, ctx: Context = None
) -> list:
    """Recent sync errors — failed record GUIDs, entity types, error messages."""
    app_ctx: AppContext = ctx.request_context.lifespan_context
    return _serialize(
        app_ctx.cache.get_sync_errors(entity_type=entity_type, limit=limit)
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
    mcp.run(transport=transport_env)
