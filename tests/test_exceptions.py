"""Tests for exceptions — SPECS.md §1."""

from tallybridge.exceptions import (
    TallyBridgeCacheError,
    TallyConnectionError,
    TallyDataError,
    TallySyncError,
)


def test_tally_connection_error_is_exception() -> None:
    assert issubclass(TallyConnectionError, Exception)


def test_tally_connection_error_message() -> None:
    err = TallyConnectionError("Could not connect to Tally on localhost:9000")
    assert "localhost:9000" in str(err)


def test_tally_connection_error_raise_catch() -> None:
    try:
        raise TallyConnectionError("test")
    except TallyConnectionError as e:
        assert str(e) == "test"


def test_tally_data_error_is_exception() -> None:
    assert issubclass(TallyDataError, Exception)


def test_tally_data_error_stores_raw_response() -> None:
    err = TallyDataError("bad data", raw_response="<LINEERROR>oops</LINEERROR>")
    assert err.raw_response == "<LINEERROR>oops</LINEERROR>"


def test_tally_data_error_stores_error_text() -> None:
    err = TallyDataError("bad data", error_text="Company not loaded")
    assert err.error_text == "Company not loaded"


def test_tally_data_error_defaults_none() -> None:
    err = TallyDataError("bad data")
    assert err.raw_response is None
    assert err.error_text is None


def test_tally_sync_error_is_exception() -> None:
    assert issubclass(TallySyncError, Exception)


def test_tally_sync_error_raise_catch() -> None:
    try:
        raise TallySyncError("corruption")
    except TallySyncError as e:
        assert str(e) == "corruption"


def test_tally_bridge_cache_error_is_exception() -> None:
    assert issubclass(TallyBridgeCacheError, Exception)


def test_tally_bridge_cache_error_raise_catch() -> None:
    try:
        raise TallyBridgeCacheError("disk full")
    except TallyBridgeCacheError as e:
        assert str(e) == "disk full"
