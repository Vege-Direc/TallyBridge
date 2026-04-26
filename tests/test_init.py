from unittest.mock import AsyncMock, MagicMock, patch

import tallybridge
from tallybridge.models.report import SyncResult


def test_connect_creates_query_object(tmp_path):
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
                    with patch("tallybridge.TallyQuery") as mock_query_cls:
                        tallybridge.connect(
                            tally_host="localhost",
                            tally_port=9000,
                            db_path=db_path,
                        )
                        mock_query_cls.assert_called_once_with(mock_cache)


def test_connect_passes_config(tmp_path):
    db_path = str(tmp_path / "test_connect2.duckdb")
    with patch("tallybridge.TallyCache") as mock_cache_cls:
        mock_cache_cls.return_value = MagicMock()
        with patch("tallybridge.TallyConnection") as mock_conn_cls:
            with patch("tallybridge.TallySyncEngine"):
                with patch("asyncio.run"):
                    with patch("tallybridge.TallyQuery"):
                        tallybridge.connect(
                            tally_host="myhost",
                            tally_port=9001,
                            db_path=db_path,
                            company="TestCo",
                        )
                        config_arg = mock_conn_cls.call_args[0][0]
                        assert config_arg.tally_host == "myhost"
                        assert config_arg.tally_port == 9001
                        assert config_arg.tally_company == "TestCo"


def test_version_defined():
    assert tallybridge.__version__ == "0.1.0"


def test_all_exports():
    for name in tallybridge.__all__:
        assert hasattr(tallybridge, name)
