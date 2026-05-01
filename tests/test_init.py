from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import tallybridge
from tallybridge.cache import TallyCache
from tallybridge.client import TallyBridge
from tallybridge.config import TallyBridgeConfig
from tallybridge.exceptions import TallyDataError
from tallybridge.models.master import TallyGroup, TallyLedger, TallyVoucherType
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
    assert tallybridge.__version__ == "0.2.0"


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
                result = await bridge.create_ledger(
                    "New Customer", "Sundry Debtors", validate=False
                )
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
                    "Sales", "20250101", entries, narration="Test", validate=False
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


def _make_bridge_with_db(tmp_path):
    db_path = str(tmp_path / "validate.duckdb")
    cache = TallyCache(db_path)
    cache.upsert_groups(
        [
            TallyGroup(
                guid="grp-sd",
                alter_id=1,
                name="Sundry Debtors",
                parent="Current Assets",
                primary_group="Assets",
            ),
            TallyGroup(
                guid="grp-sc",
                alter_id=2,
                name="Sundry Creditors",
                parent="Current Liabilities",
                primary_group="Liabilities",
            ),
        ]
    )
    cache.upsert_ledgers(
        [
            TallyLedger(
                guid="l1",
                alter_id=1,
                name="Cash",
                parent_group="Cash-in-Hand",
                closing_balance=0,
            ),
            TallyLedger(
                guid="l2",
                alter_id=2,
                name="Sharma Trading Co",
                parent_group="Sundry Debtors",
                closing_balance=0,
                gstin="27AABCS1429B1Z1",
            ),
            TallyLedger(
                guid="l3",
                alter_id=3,
                name="Sales",
                parent_group="Sales Accounts",
                closing_balance=0,
            ),
            TallyLedger(
                guid="l4",
                alter_id=4,
                name="Cash-in-Hand Ledger",
                parent_group="Cash-in-Hand",
                closing_balance=0,
            ),
        ]
    )
    cache.upsert_voucher_types(
        [
            TallyVoucherType(
                guid="vt1", alter_id=1, name="Sales", parent="Accounting Vouchers"
            ),
        ]
    )
    with (
        patch("tallybridge.client.TallyConnection"),
        patch("tallybridge.client.TallySyncEngine"),
    ):
        bridge = TallyBridge(TallyBridgeConfig(db_path=db_path))
    bridge._cache = cache
    return bridge


async def test_validate_voucher_balanced(tmp_path):
    bridge = _make_bridge_with_db(tmp_path)
    result = await bridge.validate_voucher(
        voucher_type="Sales",
        date_str="20250401",
        ledger_entries=[
            {"ledger_name": "Sharma Trading Co", "amount": "5000"},
            {"ledger_name": "Sales", "amount": "-5000"},
        ],
        party_ledger="Sharma Trading Co",
    )
    assert result.valid is True
    assert result.errors == []


async def test_validate_voucher_unbalanced(tmp_path):
    bridge = _make_bridge_with_db(tmp_path)
    result = await bridge.validate_voucher(
        voucher_type="Sales",
        date_str="20250401",
        ledger_entries=[
            {"ledger_name": "Sharma Trading Co", "amount": "5000"},
            {"ledger_name": "Sales", "amount": "-3000"},
        ],
    )
    assert result.valid is False
    assert any("Unbalanced" in e for e in result.errors)


async def test_validate_voucher_missing_ledger(tmp_path):
    bridge = _make_bridge_with_db(tmp_path)
    result = await bridge.validate_voucher(
        voucher_type="Sales",
        date_str="20250401",
        ledger_entries=[
            {"ledger_name": "NonExistent", "amount": "5000"},
            {"ledger_name": "Sales", "amount": "-5000"},
        ],
    )
    assert result.valid is False
    assert any("NonExistent" in e for e in result.errors)


async def test_validate_voucher_wrong_party_group(tmp_path):
    bridge = _make_bridge_with_db(tmp_path)
    result = await bridge.validate_voucher(
        voucher_type="Sales",
        date_str="20250401",
        ledger_entries=[
            {"ledger_name": "Cash", "amount": "5000"},
            {"ledger_name": "Sales", "amount": "-5000"},
        ],
        party_ledger="Cash",
    )
    assert "Cash-in-Hand" in "".join(result.warnings)


async def test_validate_ledger_new(tmp_path):
    bridge = _make_bridge_with_db(tmp_path)
    result = await bridge.validate_ledger("New Customer", "Sundry Debtors")
    assert result.valid is True
    assert result.errors == []


async def test_validate_ledger_duplicate(tmp_path):
    bridge = _make_bridge_with_db(tmp_path)
    result = await bridge.validate_ledger("Cash", "Cash-in-Hand")
    assert result.valid is False
    assert any("already exists" in e for e in result.errors)


async def test_validate_ledger_missing_group(tmp_path):
    bridge = _make_bridge_with_db(tmp_path)
    result = await bridge.validate_ledger("New Ledger", "NonExistent Group")
    assert result.valid is False
    assert any("NonExistent Group" in e for e in result.errors)


async def test_create_voucher_with_validation(tmp_path):
    bridge = _make_bridge_with_db(tmp_path)
    with patch.object(bridge._connection, "import_vouchers", new_callable=AsyncMock):
        with pytest.raises(TallyDataError, match="Voucher validation failed"):
            await bridge.create_voucher(
                "Sales",
                "20250401",
                [{"ledger_name": "Missing", "amount": "5000"}],
            )


async def test_create_voucher_skip_validation(tmp_path):
    bridge = _make_bridge_with_db(tmp_path)
    with patch.object(
        bridge._connection,
        "import_vouchers",
        new_callable=AsyncMock,
        return_value=ImportResult(success=True, created=1),
    ):
        result = await bridge.create_voucher(
            "Sales",
            "20250401",
            [{"ledger_name": "Missing", "amount": "5000"}],
            validate=False,
        )
        assert result.success is True
