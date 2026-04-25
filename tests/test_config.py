"""Tests for config — SPECS.md §2."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from tallybridge.config import TallyBridgeConfig, get_config, reset_config


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    reset_config()
    yield
    reset_config()


def test_default_field_values() -> None:
    config = TallyBridgeConfig()
    assert config.tally_host == "localhost"
    assert config.tally_port == 9000
    assert config.tally_company is None
    assert config.db_path == "tallybridge.duckdb"
    assert config.sync_frequency_minutes == 5
    assert config.log_level == "INFO"
    assert config.supabase_url is None
    assert config.supabase_key is None


def test_env_var_overrides_port() -> None:
    with patch.dict(os.environ, {"TALLYBRIDGE_TALLY_PORT": "9001"}):
        config = TallyBridgeConfig()
        assert config.tally_port == 9001


def test_log_level_normalised() -> None:
    with patch.dict(os.environ, {"TALLYBRIDGE_LOG_LEVEL": "debug"}):
        config = TallyBridgeConfig()
        assert config.log_level == "DEBUG"


def test_invalid_log_level_raises() -> None:
    with patch.dict(os.environ, {"TALLYBRIDGE_LOG_LEVEL": "VERBOSE"}):
        with pytest.raises(ValidationError):
            TallyBridgeConfig()


def test_invalid_port_raises() -> None:
    with patch.dict(os.environ, {"TALLYBRIDGE_TALLY_PORT": "99999"}):
        with pytest.raises(ValidationError):
            TallyBridgeConfig()


def test_get_config_returns_same_instance() -> None:
    a = get_config()
    b = get_config()
    assert a is b


def test_tally_url_property() -> None:
    config = TallyBridgeConfig(tally_host="192.168.1.10", tally_port=9001)
    assert config.tally_url == "http://192.168.1.10:9001"


async def test_validate_tally_connection_raises_when_unreachable() -> None:
    config = TallyBridgeConfig(tally_host="localhost", tally_port=19999)
    from tallybridge.exceptions import TallyConnectionError

    with pytest.raises(TallyConnectionError):
        await config.validate_tally_connection()
