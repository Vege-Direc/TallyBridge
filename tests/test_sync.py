"""Tests for sync — SPECS.md §7."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tallybridge.cache import TallyCache
from tallybridge.connection import TallyConnection
from tallybridge.exceptions import TallyConnectionError, TallyDataError
from tallybridge.parser import TallyXMLParser
from tallybridge.sync import SYNC_ORDER, TallySyncEngine
from tallybridge.version import TallyProduct


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
    cache.upsert_vouchers.return_value = (7, 100)
    return cache


@pytest.fixture
def mock_parser():
    parser = MagicMock(spec=TallyXMLParser)
    mock_ledger = MagicMock()
    mock_ledger.alter_id = 50
    mock_group = MagicMock()
    mock_group.alter_id = 50
    mock_stock_item = MagicMock()
    mock_stock_item.alter_id = 50
    mock_voucher_type = MagicMock()
    mock_voucher_type.alter_id = 50
    mock_unit = MagicMock()
    mock_unit.alter_id = 50
    mock_stock_group = MagicMock()
    mock_stock_group.alter_id = 50
    mock_cost_center = MagicMock()
    mock_cost_center.alter_id = 50
    mock_voucher = MagicMock()
    mock_voucher.alter_id = 100
    parser.parse_ledgers.return_value = [mock_ledger] * 5
    parser.parse_groups.return_value = [mock_group] * 3
    parser.parse_stock_items.return_value = [mock_stock_item] * 3
    parser.parse_voucher_types.return_value = [mock_voucher_type] * 4
    parser.parse_units.return_value = [mock_unit] * 4
    parser.parse_stock_groups.return_value = [mock_stock_group] * 2
    parser.parse_cost_centers.return_value = [mock_cost_center] * 3
    parser.parse_vouchers.return_value = [mock_voucher] * 7
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
    assert result == (0, 0)


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


async def test_sync_all_with_reconcile(
    engine: TallySyncEngine, mock_connection, mock_cache
) -> None:
    mock_connection.get_alter_id_max.return_value = 100
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    mock_cache.conn.execute.return_value.fetchone.return_value = (5,)
    results = await engine.sync_all(reconcile=True)
    assert len(results) == len(SYNC_ORDER)


async def test_voucher_batch_size_is_configurable() -> None:
    engine = TallySyncEngine(
        AsyncMock(spec=TallyConnection),
        MagicMock(spec=TallyCache),
        MagicMock(spec=TallyXMLParser),
        voucher_batch_size=2000,
    )
    assert engine._voucher_batch_size == 2000


async def test_engine_has_shutdown_event(
    mock_connection, mock_cache, mock_parser
) -> None:
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    assert hasattr(engine, "_shutdown_event")
    assert not engine._shutdown_event.is_set()
    engine.request_shutdown()
    assert engine._shutdown_event.is_set()


async def test_master_sync_uses_batching_for_large_ranges(
    mock_connection, mock_cache, mock_parser
) -> None:
    engine = TallySyncEngine(
        mock_connection, mock_cache, mock_parser, voucher_batch_size=100
    )
    mock_cache.get_last_alter_id.return_value = 0
    mock_connection.get_alter_id_max.return_value = 250
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    mock_connection.get_company_list.return_value = ["Test Co"]
    result = await engine.sync_entity("ledger")
    assert result.success is True
    assert mock_connection.export_collection.call_count >= 2


async def test_sync_all_detects_version(
    mock_connection, mock_cache, mock_parser
) -> None:
    mock_connection.get_alter_id_max.return_value = 100
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    mock_connection._detected_version = None
    mock_connection.post_xml = AsyncMock(
        return_value="<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        "<COMPANY><VERSION>TallyPrime 4.0</VERSION></COMPANY>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    await engine.sync_all()
    assert engine._detected_version is not None


async def test_sync_all_version_detection_fails_gracefully(
    mock_connection, mock_cache, mock_parser
) -> None:
    mock_connection.get_alter_id_max.return_value = 0
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    mock_connection._detected_version = None
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    with patch(
        "tallybridge.sync.detect_tally_version",
        side_effect=RuntimeError("unexpected"),
    ):
        await engine.sync_all()
    assert engine._detected_version == TallyProduct.ERP9


async def test_voucher_batched_stops_on_empty(
    mock_connection, mock_cache, mock_parser
) -> None:
    mock_cache.get_last_alter_id.return_value = 0
    mock_connection.get_alter_id_max.return_value = 15000
    call_count = 0

    async def _return_empty_then_data(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            mock_parser.parse_vouchers.return_value = [MagicMock(alter_id=100)]
            return "<ENVELOPE></ENVELOPE>"
        mock_parser.parse_vouchers.return_value = []
        return "<ENVELOPE></ENVELOPE>"

    mock_connection.export_collection.side_effect = _return_empty_then_data
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    result = await engine.sync_entity("voucher")
    assert result.success is True


async def test_master_batched_stops_on_empty(
    mock_connection, mock_cache, mock_parser
) -> None:
    mock_cache.get_last_alter_id.return_value = 0
    mock_connection.get_alter_id_max.return_value = 15000
    call_count = 0

    async def _return_empty_then_data(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            mock_parser.parse_ledgers.return_value = [MagicMock(alter_id=100)]
            return "<ENVELOPE></ENVELOPE>"
        mock_parser.parse_ledgers.return_value = []
        return "<ENVELOPE></ENVELOPE>"

    mock_connection.export_collection.side_effect = _return_empty_then_data
    engine = TallySyncEngine(
        mock_connection, mock_cache, mock_parser, voucher_batch_size=100
    )
    result = await engine.sync_entity("ledger")
    assert result.success is True


async def test_reconcile_skips_failed_entity(
    mock_connection, mock_cache, mock_parser
) -> None:
    mock_connection.get_alter_id_max.side_effect = [
        TallyConnectionError("fail"),
        100,
        100,
        100,
        100,
        100,
        100,
        100,
    ]
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    results = await engine.sync_all(reconcile=True)
    assert len(results) == len(SYNC_ORDER)


async def test_reconcile_skips_unknown_table() -> None:
    mock_conn = AsyncMock(spec=TallyConnection)
    mock_cache_local = MagicMock(spec=TallyCache)
    mock_cache_local.get_last_alter_id.return_value = 0
    mock_cache_local.upsert_ledgers.return_value = 5
    mock_cache_local.upsert_groups.return_value = 3
    mock_cache_local.upsert_stock_items.return_value = 3
    mock_cache_local.upsert_voucher_types.return_value = 4
    mock_cache_local.upsert_units.return_value = 4
    mock_cache_local.upsert_stock_groups.return_value = 2
    mock_cache_local.upsert_cost_centers.return_value = 3
    mock_cache_local.upsert_vouchers.return_value = (7, 100)
    mock_conn.get_alter_id_max.return_value = 100
    mock_conn.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    mock_cache_local.conn.execute.return_value.fetchone.return_value = (5,)
    parser_local = MagicMock(spec=TallyXMLParser)
    for name in [
        "parse_ledgers",
        "parse_groups",
        "parse_stock_items",
        "parse_voucher_types",
        "parse_units",
        "parse_stock_groups",
        "parse_cost_centers",
        "parse_vouchers",
    ]:
        getattr(parser_local, name).return_value = [MagicMock(alter_id=50)]
    engine = TallySyncEngine(mock_conn, mock_cache_local, parser_local)
    results = await engine.sync_all(reconcile=True)
    assert len(results) == len(SYNC_ORDER)


async def test_full_sync_drift_detection(
    mock_connection, mock_cache, mock_parser
) -> None:
    mock_connection.get_alter_id_max.return_value = 100
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    mock_cache.detect_content_drift.return_value = [
        {"guid": "g1", "name": "Test", "content_hash": "abc123"}
    ]
    mock_cache.compare_content_drift.return_value = [
        {
            "entity_type": "ledger",
            "guid": "g1",
            "name": "Test",
            "old_hash": "abc123",
            "new_hash": "def456",
        }
    ]
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    results = await engine.full_sync()
    assert len(results) == len(SYNC_ORDER)


async def test_full_sync_drift_detection_exception(
    mock_connection, mock_cache, mock_parser
) -> None:
    mock_connection.get_alter_id_max.return_value = 100
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    mock_cache.detect_content_drift.side_effect = Exception("drift failed")
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    results = await engine.full_sync()
    assert len(results) == len(SYNC_ORDER)


async def test_get_active_company_no_company_returns_none(
    engine: TallySyncEngine, mock_connection
) -> None:
    engine._company = None
    mock_connection.get_company_list.return_value = []
    result = await engine.get_active_company()
    assert result is None


async def test_get_active_company_exception_returns_none(
    engine: TallySyncEngine, mock_connection
) -> None:
    engine._company = None
    mock_connection.get_company_list.side_effect = ConnectionError("fail")
    result = await engine.get_active_company()
    assert result is None


async def test_ensure_company_auto_detects(
    engine: TallySyncEngine, mock_connection
) -> None:
    engine._company = None
    mock_connection.get_company_list.return_value = ["Auto Detected Co"]
    result = await engine._ensure_company()
    assert result == "Auto Detected Co"
    assert engine._company == "Auto Detected Co"


async def test_ensure_company_exception_logs_warning(
    engine: TallySyncEngine, mock_connection
) -> None:
    engine._company = None
    mock_connection.get_company_list.side_effect = ConnectionError("fail")
    result = await engine._ensure_company()
    assert result is None


async def test_voucher_batch_size_fallback_on_config_error() -> None:
    import tallybridge.sync as sync_mod

    original = sync_mod.get_config
    sync_mod.get_config = lambda: (_ for _ in ()).throw(RuntimeError("no config"))
    try:
        engine = TallySyncEngine(
            AsyncMock(spec=TallyConnection),
            MagicMock(spec=TallyCache),
            MagicMock(spec=TallyXMLParser),
        )
        assert engine._voucher_batch_size == 5000
    finally:
        sync_mod.get_config = original


async def test_run_continuous_with_shutdown(
    mock_connection, mock_cache, mock_parser
) -> None:
    mock_connection.get_alter_id_max.return_value = 0
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    engine.request_shutdown()
    await engine.run_continuous(frequency_minutes=1)


async def test_run_continuous_completes_one_cycle(
    mock_connection, mock_cache, mock_parser
) -> None:
    sync_count = 0

    async def _sync_once_then_shutdown():
        nonlocal sync_count
        sync_count += 1
        if sync_count >= 1:
            engine.request_shutdown()
        return {}

    mock_connection.get_alter_id_max.return_value = 0
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    engine.sync_all = _sync_once_then_shutdown
    await engine.run_continuous(frequency_minutes=1)
    assert sync_count >= 1


async def test_run_continuous_circuit_breaker_on_error_then_shutdown(
    mock_connection, mock_cache, mock_parser
) -> None:
    call_count = 0

    async def _fail_then_shutdown():
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            raise TallyConnectionError("connection lost")
        engine.request_shutdown()
        return {}

    mock_connection.get_alter_id_max.return_value = 0
    mock_connection.export_collection.return_value = "<ENVELOPE></ENVELOPE>"
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    engine.sync_all = _fail_then_shutdown
    await engine.run_continuous(frequency_minutes=1)
    assert call_count >= 2


async def test_sync_master_batched_unknown_entity_type(
    mock_connection, mock_cache, mock_parser
) -> None:
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    count, max_id = await engine._sync_master_batched("nonexistent", 0, 100)
    assert count == 0
    assert max_id == 0


async def test_detect_deletions(mock_connection, mock_cache, mock_parser) -> None:
    mock_connection.export_collection.return_value = (
        "<ENVELOPE><BODY><DATA><COLLECTION>"
        "<LEDGER NAME='A'><GUID>g1</GUID></LEDGER>"
        "<LEDGER NAME='B'><GUID>g2</GUID></LEDGER>"
        "</COLLECTION></DATA></BODY></ENVELOPE>"
    )
    mock_cache.get_cached_guids.return_value = {"g1", "g2", "g3"}
    mock_cache.delete_records_by_guid.return_value = 1
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    deletions = await engine.detect_deletions(entity_types=["ledger"])
    assert deletions["ledger"] == 1
    mock_cache.delete_records_by_guid.assert_called_once_with("ledger", {"g3"})


async def test_detect_deletions_no_orphans(
    mock_connection, mock_cache, mock_parser
) -> None:
    mock_connection.export_collection.return_value = (
        "<ENVELOPE><BODY><DATA><COLLECTION>"
        "<LEDGER NAME='A'><GUID>g1</GUID></LEDGER>"
        "</COLLECTION></DATA></BODY></ENVELOPE>"
    )
    mock_cache.get_cached_guids.return_value = {"g1"}
    engine = TallySyncEngine(mock_connection, mock_cache, mock_parser)
    deletions = await engine.detect_deletions(entity_types=["ledger"])
    assert deletions["ledger"] == 0


def test_extract_guids() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><COLLECTION>"
        "<LEDGER><GUID>g1</GUID></LEDGER>"
        "<LEDGER><GUID>g2</GUID></LEDGER>"
        "</COLLECTION></DATA></BODY></ENVELOPE>"
    )
    guids = TallySyncEngine._extract_guids(xml)
    assert guids == {"g1", "g2"}


def test_extract_guids_invalid_xml() -> None:
    guids = TallySyncEngine._extract_guids("<invalid")
    assert guids == set()
