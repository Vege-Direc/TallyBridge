"""Integration tests — SPECS.md §11c."""

from datetime import date
from decimal import Decimal

import pytest
from pytest_httpserver import HTTPServer

from tallybridge.cache import TallyCache
from tallybridge.config import TallyBridgeConfig
from tallybridge.connection import TallyConnection
from tallybridge.parser import TallyXMLParser
from tallybridge.query import TallyQuery
from tallybridge.sync import TallySyncEngine
from tests.mock_tally import setup_mock_routes


@pytest.fixture
def mock_server(httpserver: HTTPServer):
    setup_mock_routes(httpserver)
    return httpserver


@pytest.fixture
def int_db(tmp_path):
    cache = TallyCache(str(tmp_path / "int_test.duckdb"))
    yield cache
    cache.close()


async def test_full_end_to_end(mock_server: HTTPServer, int_db: TallyCache) -> None:
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
    )
    connection = TallyConnection(config)
    parser = TallyXMLParser()
    engine = TallySyncEngine(connection, int_db, parser)

    results = await engine.sync_all()

    for entity_type in [
        "ledger",
        "group",
        "unit",
        "stock_group",
        "stock_item",
        "cost_center",
    ]:
        assert results[entity_type].success, (
            f"{entity_type} sync failed: {results[entity_type].error_message}"
        )

    assert results["ledger"].records_synced > 0
    assert results["group"].records_synced > 0
    assert results["unit"].records_synced > 0
    assert results["stock_item"].records_synced > 0

    query = TallyQuery(int_db)
    digest = query.get_daily_digest(date(2025, 12, 31))
    assert digest.total_sales > 0

    receivables = query.get_receivables()
    assert len(receivables) > 0

    await connection.close()


async def test_cancelled_voucher_excluded(
    mock_server: HTTPServer, int_db: TallyCache
) -> None:
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
    )
    connection = TallyConnection(config)
    parser = TallyXMLParser()
    engine = TallySyncEngine(connection, int_db, parser)
    await engine.sync_all()
    await connection.close()

    query = TallyQuery(int_db)
    digest = query.get_daily_digest(date(2025, 12, 31))
    expected_sales = Decimal("50000") + Decimal("35000") + Decimal("25000")
    assert digest.total_sales == expected_sales
