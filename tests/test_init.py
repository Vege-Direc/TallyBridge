from unittest.mock import AsyncMock, MagicMock, patch

import tallybridge
from tallybridge.client import TallyBridge
from tallybridge.models.report import ImportResult, SyncResult


def test_connect_returns_tallybridge(tmp_path):
    db_path = str(tmp_path / "test_connect.duckdb")
    with patch("tallybridge.TallyCache") as mock_cache_cls:
        mock_cache = MagicMock()
        mock_cache_cls.return_value = mock_cache
        with patch("tallybridge.TallyConnection"):
            with patch("tallybridge.TallySyncEngine") as mock_engine_cls:
                mock_engine = MagicMock()
                mock_engine_cls.return_value = mock_engine
                mock_engine.sync_all = AsyncMock(
                    return_value={"ledger": SyncResult(entity_type="ledger")}
                )
                with patch("asyncio.run"):
                    result = tallybridge.connect(
                        tally_host="localhost",
                        tally_port=9000,
                        db_path=db_path,
                    )
                    assert isinstance(result, TallyBridge)


def test_connect_passes_config(tmp_path):
    db_path = str(tmp_path / "test_connect2.duckdb")
    with patch("tallybridge.TallyBridge") as mock_bridge_cls:
        mock_bridge = MagicMock()
        mock_bridge_cls.return_value = mock_bridge
        mock_bridge.sync = AsyncMock(
            return_value={"ledger": SyncResult(entity_type="ledger")}
        )
        with patch("asyncio.run"):
            tallybridge.connect(
                tally_host="myhost",
                tally_port=9001,
                db_path=db_path,
                company="TestCo",
            )
            config_arg = mock_bridge_cls.call_args[0][0]
            assert config_arg.tally_host == "myhost"
            assert config_arg.tally_port == 9001
            assert config_arg.tally_company == "TestCo"


def test_version_defined():
    assert tallybridge.__version__ == "0.1.0"


def test_all_exports():
    for name in tallybridge.__all__:
        assert hasattr(tallybridge, name)


def test_tallybridge_creates_and_queries(tmp_path):
    db_path = str(tmp_path / "test_bridge.duckdb")
    with patch("tallybridge.client.TallyCache") as mock_cache_cls:
        mock_cache = MagicMock()
        mock_cache_cls.return_value = mock_cache
        mock_cache.query.return_value = [{"name": "Cash", "closing_balance": 45000}]
        with patch("tallybridge.client.TallyConnection"):
            with patch("tallybridge.client.TallySyncEngine"):
                bridge = TallyBridge(tallybridge.TallyBridgeConfig(db_path=db_path))
                result = bridge.search("Cash")
                assert isinstance(result, dict)


async def test_tallybridge_sync(tmp_path):
    db_path = str(tmp_path / "test_bridge_sync.duckdb")
    with patch("tallybridge.client.TallyCache") as mock_cache_cls:
        mock_cache_cls.return_value = MagicMock()
        with patch("tallybridge.client.TallyConnection"):
            with patch("tallybridge.client.TallySyncEngine") as mock_engine_cls:
                mock_engine = MagicMock()
                mock_engine_cls.return_value = mock_engine
                mock_engine.sync_all = AsyncMock(
                    return_value={"ledger": SyncResult(entity_type="ledger")}
                )
                bridge = TallyBridge(tallybridge.TallyBridgeConfig(db_path=db_path))
                result = await bridge.sync()
                assert "ledger" in result
                mock_engine.sync_all.assert_called_once()


async def test_tallybridge_sync_full(tmp_path):
    db_path = str(tmp_path / "test_bridge_full.duckdb")
    with patch("tallybridge.client.TallyCache") as mock_cache_cls:
        mock_cache_cls.return_value = MagicMock()
        with patch("tallybridge.client.TallyConnection"):
            with patch("tallybridge.client.TallySyncEngine") as mock_engine_cls:
                mock_engine = MagicMock()
                mock_engine_cls.return_value = mock_engine
                mock_engine.full_sync = AsyncMock(
                    return_value={"ledger": SyncResult(entity_type="ledger")}
                )
                bridge = TallyBridge(tallybridge.TallyBridgeConfig(db_path=db_path))
                await bridge.sync(full=True)
                mock_engine.full_sync.assert_called_once()


async def test_tallybridge_create_ledger(tmp_path):
    db_path = str(tmp_path / "test_bridge_cl.duckdb")
    with patch("tallybridge.client.TallyCache") as mock_cache_cls:
        mock_cache_cls.return_value = MagicMock()
        with patch("tallybridge.client.TallyConnection") as mock_conn_cls:
            mock_conn = MagicMock()
            mock_conn_cls.return_value = mock_conn
            mock_conn.import_masters = AsyncMock(
                return_value=ImportResult(success=True, created=1)
            )
            with patch("tallybridge.client.TallySyncEngine"):
                bridge = TallyBridge(tallybridge.TallyBridgeConfig(db_path=db_path))
                result = await bridge.create_ledger("New Customer", "Sundry Debtors")
                assert result.success is True
                assert result.created == 1
                mock_conn.import_masters.assert_called_once()


async def test_tallybridge_create_voucher(tmp_path):
    db_path = str(tmp_path / "test_bridge_cv.duckdb")
    with patch("tallybridge.client.TallyCache") as mock_cache_cls:
        mock_cache_cls.return_value = MagicMock()
        with patch("tallybridge.client.TallyConnection") as mock_conn_cls:
            mock_conn = MagicMock()
            mock_conn_cls.return_value = mock_conn
            mock_conn.import_vouchers = AsyncMock(
                return_value=ImportResult(success=True, created=1)
            )
            with patch("tallybridge.client.TallySyncEngine"):
                bridge = TallyBridge(tallybridge.TallyBridgeConfig(db_path=db_path))
                entries = [{"ledger_name": "Cash", "amount": "5000"}]
                result = await bridge.create_voucher(
                    "Sales", "20250101", entries, narration="Test"
                )
                assert result.success is True
                mock_conn.import_vouchers.assert_called_once()


async def test_tallybridge_cancel_voucher(tmp_path):
    db_path = str(tmp_path / "test_bridge_cdv.duckdb")
    with patch("tallybridge.client.TallyCache") as mock_cache_cls:
        mock_cache_cls.return_value = MagicMock()
        with patch("tallybridge.client.TallyConnection") as mock_conn_cls:
            mock_conn = MagicMock()
            mock_conn_cls.return_value = mock_conn
            mock_conn.import_vouchers = AsyncMock(
                return_value=ImportResult(success=True, altered=1)
            )
            with patch("tallybridge.client.TallySyncEngine"):
                bridge = TallyBridge(tallybridge.TallyBridgeConfig(db_path=db_path))
                result = await bridge.cancel_voucher("guid-abc-123")
                assert result.success is True
                mock_conn.import_vouchers.assert_called_once()


async def test_tallybridge_context_manager(tmp_path):
    db_path = str(tmp_path / "test_bridge_cm.duckdb")
    with patch("tallybridge.client.TallyCache") as mock_cache_cls:
        mock_cache = MagicMock()
        mock_cache_cls.return_value = mock_cache
        with patch("tallybridge.client.TallyConnection") as mock_conn_cls:
            mock_conn = MagicMock()
            mock_conn_cls.return_value = mock_conn
            mock_conn.close = AsyncMock()
            with patch("tallybridge.client.TallySyncEngine"):
                async with TallyBridge(
                    tallybridge.TallyBridgeConfig(db_path=db_path)
                ) as bridge:
                    assert isinstance(bridge, TallyBridge)
                mock_conn.close.assert_called_once()
                mock_cache.close.assert_called_once()


async def test_connection_context_manager():
    config = tallybridge.TallyBridgeConfig()
    conn = tallybridge.TallyConnection(config)
    conn._client = AsyncMock()
    async with conn:
        pass
    conn._client.aclose.assert_called()
