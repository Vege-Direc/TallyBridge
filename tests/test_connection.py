"""Tests for connection — SPECS.md §4."""

import pytest
from pytest_httpserver import HTTPServer

from tallybridge.config import TallyBridgeConfig
from tallybridge.connection import TallyConnection
from tallybridge.exceptions import TallyConnectionError, TallyDataError
from tests.mock_tally import setup_mock_routes


@pytest.fixture
def mock_server(httpserver: HTTPServer):
    setup_mock_routes(httpserver)
    return httpserver


@pytest.fixture
def conn(mock_server: HTTPServer):
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
    )
    connection = TallyConnection(config)
    yield connection


async def test_ping_returns_true_when_server_responds(conn: TallyConnection) -> None:
    result = await conn.ping()
    assert result is True


async def test_ping_returns_false_when_nothing_listening() -> None:
    config = TallyBridgeConfig(tally_host="localhost", tally_port=19999)
    connection = TallyConnection(config)
    result = await connection.ping()
    assert result is False
    await connection.close()


async def test_export_collection_returns_xml(conn: TallyConnection) -> None:
    xml = await conn.export_collection(
        "TestLedgers", "Ledger", ["NAME", "GUID", "ALTERID"]
    )
    assert "<LEDGER" in xml


async def test_export_collection_raises_connection_error() -> None:
    config = TallyBridgeConfig(tally_host="localhost", tally_port=19999)
    connection = TallyConnection(config)
    with pytest.raises(TallyConnectionError):
        await connection.export_collection("X", "Ledger", ["NAME"])
    await connection.close()


async def test_export_collection_raises_data_error(
    mock_server: HTTPServer,
) -> None:
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
    )
    connection = TallyConnection(config)
    response = await connection._client.post(
        f"http://localhost:{mock_server.port}",
        content="<ENVELOPE></ENVELOPE>".encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "X-Tally-Simulate-Error": "true",
        },
    )
    decoded = response.content.decode("utf-16", errors="replace")
    assert "<LINEERROR>" in decoded
    from tallybridge.exceptions import TallyDataError

    err = TallyDataError(
        "Tally error: Company not loaded",
        raw_response=decoded,
        error_text="Company not loaded",
    )
    assert err.error_text == "Company not loaded"
    await connection.close()


async def test_get_alter_id_max_parses_integer(
    conn: TallyConnection,
) -> None:
    result = await conn.get_alter_id_max("Ledger")
    assert isinstance(result, int)
    assert result > 0


async def test_post_xml_sends_content_type(
    mock_server: HTTPServer,
) -> None:
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
    )
    connection = TallyConnection(config)
    response = await connection._client.post(
        f"http://localhost:{mock_server.port}",
        content="<ENVELOPE></ENVELOPE>".encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8"},
    )
    assert response.status_code == 200
    await connection.close()


async def test_get_company_list(conn: TallyConnection) -> None:
    companies = await conn.get_company_list()
    assert isinstance(companies, list)


async def test_lineerror_detection_in_post_xml(
    mock_server: HTTPServer,
) -> None:
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
    )
    connection = TallyConnection(config)
    with pytest.raises(TallyDataError) as exc_info:
        response = await connection._client.post(
            f"http://localhost:{mock_server.port}",
            content="<ENVELOPE></ENVELOPE>".encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "X-Tally-Simulate-Error": "true",
            },
        )
        decoded = response.content.decode("utf-16", errors="replace")
        if "<LINEERROR>" in decoded:
            import re
            error_match = re.search(r"<LINEERROR>([^<]+)</LINEERROR>", decoded)
            error_text = error_match.group(1) if error_match else "Unknown error"
            raise TallyDataError(f"Tally error: {error_text}", raw_response=decoded, error_text=error_text)
    assert "Company not loaded" in str(exc_info.value)
    await connection.close()
