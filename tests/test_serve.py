"""Tests for serve module — HTTP API bridge."""

from unittest.mock import MagicMock, patch

import pytest


def _make_mock_cache() -> MagicMock:
    mock_cache = MagicMock()
    mock_cache.health_check.return_value = {
        "db_size_mb": 1.0,
        "total_records": 100,
    }
    mock_cache.query_readonly.return_value = [
        {"name": "Test", "amount": 1000},
    ]
    mock_cache.initialize.return_value = None
    return mock_cache


@pytest.fixture
def mock_cache():
    return _make_mock_cache()


@pytest.fixture
def app_with_cache(mock_cache):
    from tallybridge.serve import app, reset_cache

    reset_cache()
    with patch("tallybridge.serve._get_cache", return_value=mock_cache):
        yield app
    reset_cache()


async def test_root(app_with_cache) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_with_cache)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "TallyBridge API"


async def test_health(app_with_cache) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_with_cache)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


async def test_list_views(app_with_cache) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_with_cache)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/views")
    assert resp.status_code == 200
    data = resp.json()
    assert "v_sales_summary" in data["views"]
    assert "v_receivables" in data["views"]


async def test_query_view(app_with_cache) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_with_cache)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/views/v_sales_summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["row_count"] >= 0


async def test_query_view_not_found(app_with_cache) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_with_cache)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/views/nonexistent")
    assert resp.status_code == 404


async def test_execute_query(app_with_cache) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_with_cache)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/query",
            json={"sql": "SELECT * FROM mst_ledger LIMIT 5"},
        )
    assert resp.status_code == 200


async def test_execute_query_empty(app_with_cache) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_with_cache)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/query", json={"sql": ""})
    assert resp.status_code == 400


async def test_execute_query_forbidden(app_with_cache) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_with_cache)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/query",
            json={"sql": "DROP TABLE mst_ledger"},
        )
    assert resp.status_code == 403


async def test_execute_query_insert_forbidden(app_with_cache) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_with_cache)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/query",
            json={"sql": "INSERT INTO mst_ledger VALUES (1, 'x')"},
        )
    assert resp.status_code == 403


async def test_execute_query_update_forbidden(app_with_cache) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_with_cache)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/query",
            json={"sql": "UPDATE mst_ledger SET name='x'"},
        )
    assert resp.status_code == 403


async def test_list_tables(app_with_cache, mock_cache) -> None:
    from httpx import ASGITransport, AsyncClient

    mock_cache.query_readonly.return_value = [
        {"table_name": "mst_ledger", "estimated_size": 1000},
    ]
    transport = ASGITransport(app=app_with_cache)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/tables")
    assert resp.status_code == 200


async def test_query_view_with_pagination(app_with_cache) -> None:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app_with_cache)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/views/v_receivables?limit=10&offset=5")
    assert resp.status_code == 200


def test_serve_command_missing_deps() -> None:
    from typer.testing import CliRunner

    from tallybridge.cli import app

    runner = CliRunner()
    with patch.dict("sys.modules", {"uvicorn": None}):
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 1 or "not installed" in result.output
