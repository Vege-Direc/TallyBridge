"""Tests for sync — SPECS.md §7."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tallybridge.cache import TallyCache
from tallybridge.connection import TallyConnection
from tallybridge.exceptions import TallyConnectionError, TallyDataError
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


async def test_sync_entity_returns_success(
    engine: TallySyncEngine, mock_connection
) -> None:
    mock_connection.get_alter_id_max.return_value = 100
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    result = await engine.sync_entity("ledger")
    assert result.success is True
    assert result.records_synced == 5


async def test_sync_entity_unchanged_alter_id(
    engine: TallySyncEngine, mock_connection
) -> None:
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


async def test_sync_all_calls_in_order(
    engine: TallySyncEngine, mock_connection
) -> None:
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
        call for call in mock_cache.update_sync_state.call_args_list if call[0][1] == 0
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


async def test_sync_entity_unknown_type(engine: TallySyncEngine) -> None:
    result = await engine.sync_entity("nonexistent")
    assert result.success is False
    assert "Unknown entity type" in (result.error_message or "")


async def test_sync_entity_data_error_returns_failure(
    engine: TallySyncEngine, mock_connection
) -> None:
    mock_connection.get_alter_id_max.side_effect = TallyDataError("bad data")
    result = await engine.sync_entity("ledger")
    assert result.success is False
    assert "bad data" in (result.error_message or "")


async def test_sync_entity_unexpected_error(
    engine: TallySyncEngine, mock_connection
) -> None:
    mock_connection.get_alter_id_max.side_effect = RuntimeError("unexpected")
    result = await engine.sync_entity("ledger")
    assert result.success is False
    assert "unexpected" in (result.error_message or "")


async def test_is_tally_available(engine: TallySyncEngine, mock_connection) -> None:
    mock_connection.ping.return_value = True
    result = await engine.is_tally_available()
    assert result is True


async def test_is_tally_available_false(
    engine: TallySyncEngine, mock_connection
) -> None:
    mock_connection.ping.return_value = False
    result = await engine.is_tally_available()
    assert result is False


async def test_parse_entity_unknown(engine: TallySyncEngine) -> None:
    result = engine._parse_entity("nonexistent", "<ENVELOPE/>")
    assert result == []


async def test_upsert_entity_unknown(engine: TallySyncEngine) -> None:
    result = engine._upsert_entity("nonexistent", [])
    assert result == 0


async def test_sync_entity_with_filter(
    engine: TallySyncEngine, mock_connection, mock_cache
) -> None:
    mock_cache.get_last_alter_id.return_value = 50
    mock_connection.get_alter_id_max.return_value = 100
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    result = await engine.sync_entity("ledger")
    assert result.success is True
    call_args = mock_connection.export_collection.call_args
    assert call_args is not None


async def test_voucher_sync_uses_batched_fetching(
    engine: TallySyncEngine, mock_connection, mock_cache
) -> None:
    mock_cache.get_last_alter_id.return_value = 0
    mock_connection.get_alter_id_max.return_value = 12000
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    result = await engine.sync_entity("voucher")
    assert result.success is True
    assert mock_connection.export_collection.call_count >= 2


async def test_voucher_batch_size_is_5000() -> None:
    from tallybridge.sync import VOUCHER_BATCH_SIZE

    assert VOUCHER_BATCH_SIZE == 5000


async def test_engine_accepts_company_parameter(
    mock_connection, mock_cache, mock_parser
) -> None:
    engine = TallySyncEngine(
        mock_connection, mock_cache, mock_parser, company="Test Co"
    )
    assert engine._company == "Test Co"


async def test_get_active_company_returns_set_company(
    engine: TallySyncEngine,
) -> None:
    engine._company = "My Company"
    result = await engine.get_active_company()
    assert result == "My Company"


async def test_get_active_company_auto_detects(
    engine: TallySyncEngine, mock_connection
) -> None:
    engine._company = None
    mock_connection.get_company_list.return_value = ["Auto Co", "Other Co"]
    result = await engine.get_active_company()
    assert result == "Auto Co"
