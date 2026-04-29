"""Read-only HTTP API bridge for BI tools — see TASKS.md 11j."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tallybridge.cache import TallyCache
from tallybridge.config import get_config

app = FastAPI(
    title="TallyBridge API",
    description="Read-only HTTP SQL API for querying synced TallyPrime data.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    sql: str


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int


class ViewsResponse(BaseModel):
    views: list[str]
    description: dict[str, str]


VIEW_DESCRIPTIONS: dict[str, str] = {
    "v_sales_summary": "Sales and credit note vouchers with amounts",
    "v_receivables": "Outstanding receivables with overdue days",
    "v_gst_summary": "GST ledger totals by date",
    "v_stock_summary": "Stock items with quantities and values",
    "v_party_position": "Party receivable/payable classification",
}

_cache: TallyCache | None = None


def _get_cache() -> TallyCache:
    global _cache
    if _cache is None:
        cfg = get_config()
        _cache = TallyCache(cfg.db_path)
        _cache.initialize()
    return _cache


def reset_cache() -> None:
    global _cache
    _cache = None


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "TallyBridge API", "version": "0.1.0"}


@app.get("/health")
async def health() -> dict[str, Any]:
    cache = _get_cache()
    health_data = cache.health_check()
    return {"status": "ok", "health": health_data}


@app.get("/views", response_model=ViewsResponse)
async def list_views() -> ViewsResponse:
    return ViewsResponse(
        views=list(VIEW_DESCRIPTIONS.keys()),
        description=VIEW_DESCRIPTIONS,
    )


@app.get("/views/{view_name}")
async def query_view(
    view_name: str,
    limit: int = Query(default=1000, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
) -> QueryResponse:
    if view_name not in VIEW_DESCRIPTIONS:
        available = list(VIEW_DESCRIPTIONS.keys())
        raise HTTPException(
            status_code=404,
            detail=f"View '{view_name}' not found. Available: {available}",
        )
    cache = _get_cache()
    try:
        results = cache.query_readonly(
            f'SELECT * FROM "{view_name}" LIMIT {limit} OFFSET {offset}'
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not results:
        return QueryResponse(columns=[], rows=[], row_count=0)

    columns = list(results[0].keys())
    rows = [[row[col] for col in columns] for row in results]
    return QueryResponse(columns=columns, rows=rows, row_count=len(rows))


@app.post("/query", response_model=QueryResponse)
async def execute_query(request: QueryRequest) -> QueryResponse:
    sql = request.sql.strip()
    if not sql:
        raise HTTPException(status_code=400, detail="SQL query cannot be empty")

    sql_upper = sql.upper()
    forbidden_keywords = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "CREATE",
        "ALTER",
        "ATTACH",
        "DETACH",
        "COPY",
        "EXPORT",
    ]
    for kw in forbidden_keywords:
        if sql_upper.startswith(kw) or f" {kw} " in f" {sql_upper} ":
            raise HTTPException(
                status_code=403,
                detail=f"Write operation '{kw}' is not allowed. This API is read-only.",
            )

    cache = _get_cache()
    try:
        results = cache.query_readonly(sql)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not results:
        return QueryResponse(columns=[], rows=[], row_count=0)

    columns = list(results[0].keys())
    rows = [[row[col] for col in columns] for row in results]
    return QueryResponse(columns=columns, rows=rows, row_count=len(rows))


@app.get("/tables")
async def list_tables() -> dict[str, Any]:
    cache = _get_cache()
    try:
        results = cache.query_readonly(
            "SELECT table_name, estimated_size "
            "FROM information_schema.tables "
            "WHERE table_schema = 'main' "
            "ORDER BY table_name"
        )
    except Exception:
        results = cache.query_readonly(
            "SELECT name AS table_name FROM sqlite_master "
            "WHERE type='table' ORDER BY name"
        )
    return {"tables": [dict(r) for r in results]}
