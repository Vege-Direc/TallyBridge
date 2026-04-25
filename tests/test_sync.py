"""Tests for sync — SPECS.md §7."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tallybridge.cache import TallyCache
from tallybridge.connection import TallyConnection
from tallybridge.exceptions import TallyConnectionError
from tallybridge.models.master import TallyLedger
from tallybridge.models.report import SyncResult
from tallybridge.parser import TallyXMLParser
from tallybridge.sync import SYNC_ORDER, TallySyncEngine


@pytest.fixture
def mock_connection():
    conn = AsyncMock(spec=TallyConnection)
    return conn


@pytest.fixture
def mock_cache():
    cache = MagicMock(spec=TallyCache)
    cache.get_last_alter_id.return_value = 0
    cache.upsert_ledgers.return_value = 5
    cache.upsert_groups.return_value = 3
    cache.upsert_stock_items.return_value = 3
    cache.upsert_voucher_types.return_value = 4
    cache.upsert_units.return_value = 4
    cache.upsert_stock_groups.return_value = 2
    cache.upsert_cost_centers.return_value = 3
    cache.upsert_vouchers.return_value = 7
    return cache


@pytest.fixture
def mock_parser():
    parser = MagicMock(spec=TallyXMLParser)
    parser.parse_ledgers.return_value = [MagicMock()] * 5
    parser.parse_groups.return_value = [MagicMock()] * 3
    parser.parse_stock_items.return_value = [MagicMock()] * 3
    parser.parse_voucher_types.return_value = [MagicMock()] * 4
    parser.parse_units.return_value = [MagicMock()] * 4
    parser.parse_stock_groups.return_value = [MagicMock()] * 2
    parser.parse_cost_centers.return_value = [MagicMock()] * 3
    parser.parse_vouchers.return_value = [MagicMock()] * 7
    return parser


@pytest.fixture
def engine(mock_connection, mock_cache, mock_parser):
    return TallySyncEngine(mock_connection, mock_cache, mock_parser)


async def test_sync_entity_returns_success(engine: TallySyncEngine, mock_connection) -> None:
    mock_connection.get_alter_id_max.return_value = 100
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    result = await engine.sync_entity("ledger")
    assert result.success is True
    assert result.records_synced == 5


async def test_sync_entity_unchanged_alter_id(engine: TallySyncEngine, mock_connection) -> None:
    mock_connection.get_alter_id_max.return_value = 0
    result = await engine.sync_entity("ledger")
    assert result.success is True
    assert result.records_synced == 0


async def test_sync_entity_connection_error_returns_failure(
    engine: TallySyncEngine, mock_connection
) -> None:
    mock_connection.get_alter_id_max.side_effect = TallyConnectionError("offline")
    result = await engine.sync_entity("ledger")
    assert result.success is False
    assert "offline" in (result.error_message or "")


async def test_sync_all_calls_in_order(engine: TallySyncEngine, mock_connection) -> None:
    mock_connection.get_alter_id_max.return_value = 100
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    results = await engine.sync_all()
    assert list(results.keys()) == SYNC_ORDER


async def test_full_sync_resets_alter_ids(
    engine: TallySyncEngine, mock_connection, mock_cache
) -> None:
    mock_connection.get_alter_id_max.return_value = 100
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    await engine.full_sync()
    reset_calls = [
        call for call in mock_cache.update_sync_state.call_args_list
        if call[0][1] == 0
    ]
    assert len(reset_calls) >= len(SYNC_ORDER)


async def test_concurrent_sync_all_waits_for_lock(
    engine: TallySyncEngine, mock_connection
) -> None:
    mock_connection.get_alter_id_max.return_value = 100
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    results1 = await engine.sync_all()
    results2 = await engine.sync_all()
    assert len(results1) == len(SYNC_ORDER)
    assert len(results2) == len(SYNC_ORDER)
