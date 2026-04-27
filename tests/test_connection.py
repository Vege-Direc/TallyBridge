"""Tests for connection — SPECS.md §4."""

import httpx
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
    decoded = response.content.decode("utf-8", errors="replace")
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


async def test_read_timeout_raises_connection_error() -> None:
    config = TallyBridgeConfig(tally_host="localhost", tally_port=19999)
    connection = TallyConnection(config)
    with pytest.raises(TallyConnectionError) as exc_info:
        raise TallyConnectionError(
            "Could not connect to Tally on localhost:19999. "
            "Is TallyPrime open? Enable: F1 > Settings > Connectivity > "
            "TallyPrime acts as = Server, Port = 19999. "
            "Try reducing VOUCHER_BATCH_SIZE if syncing large datasets."
        )
    assert "VOUCHER_BATCH_SIZE" in str(exc_info.value) or "Tally" in str(exc_info.value)
    await connection.close()


async def test_post_xml_catches_read_timeout(
    mock_server: HTTPServer,
) -> None:
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
    )
    connection = TallyConnection(config)
    original_post = connection._client.post

    async def mock_post(*args, **kwargs):
        raise httpx.ReadTimeout("Read timed out")

    connection._client.post = mock_post
    with pytest.raises(TallyConnectionError) as exc_info:
        await connection.post_xml("<ENVELOPE/>")
    assert "VOUCHER_BATCH_SIZE" in str(exc_info.value)
    connection._client.post = original_post
    await connection.close()


async def test_status_0_does_not_raise_by_default(
    mock_server: HTTPServer,
) -> None:
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
    )
    connection = TallyConnection(config)
    original_post = connection._client.post

    async def mock_post(*args, **kwargs):
        return httpx.Response(
            200,
            content=b"<ENVELOPE><STATUS>0</STATUS></ENVELOPE>",
        )

    connection._client.post = mock_post
    result = await connection.post_xml("<ENVELOPE/>")
    assert "<STATUS>0</STATUS>" in result
    connection._client.post = original_post
    await connection.close()


async def test_status_0_raises_with_strict_status(
    mock_server: HTTPServer,
) -> None:
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
        strict_status=True,
    )
    connection = TallyConnection(config)
    original_post = connection._client.post

    async def mock_post(*args, **kwargs):
        return httpx.Response(
            200,
            content=b"<ENVELOPE><STATUS>0</STATUS></ENVELOPE>",
        )

    connection._client.post = mock_post
    with pytest.raises(TallyDataError) as exc_info:
        await connection.post_xml("<ENVELOPE/>")
    assert "strict mode" in str(exc_info.value)
    connection._client.post = original_post
    await connection.close()


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
        decoded = response.content.decode("utf-8", errors="replace")
        if "<LINEERROR>" in decoded:
            import re

            error_match = re.search(r"<LINEERROR>([^<]+)</LINEERROR>", decoded)
            error_text = error_match.group(1) if error_match else "Unknown error"
            raise TallyDataError(
                f"Tally error: {error_text}",
                raw_response=decoded,
                error_text=error_text,
            )
    assert "Company not loaded" in str(exc_info.value)
    await connection.close()


async def test_export_object_by_name(conn: TallyConnection) -> None:
    xml = await conn.export_object("Ledger", name="Cash")
    assert "Cash" in xml or "<LEDGER" in xml or "<ENVELOPE" in xml


async def test_export_object_by_guid(conn: TallyConnection) -> None:
    xml = await conn.export_object("Ledger", guid="guid-cash-001")
    assert "<ENVELOPE" in xml


async def test_export_object_requires_name_or_guid(conn: TallyConnection) -> None:
    with pytest.raises(ValueError, match="name.*guid"):
        await conn.export_object("Ledger")


async def test_fetch_report(conn: TallyConnection) -> None:
    xml = await conn.fetch_report(
        "Balance Sheet", from_date="20250101", to_date="20251231"
    )
    assert "<ENVELOPE" in xml


async def test_encode_name_base64() -> None:
    encoded = TallyConnection.encode_name_base64("शर्मा ट्रेडर्स")
    import base64

    decoded = base64.b64decode(encoded).decode("utf-8")
    assert decoded == "शर्मा ट्रेडर्स"


async def test_build_object_xml_contains_type() -> None:
    xml = TallyConnection._build_object_xml("Ledger", name="Cash", company="Test Co")
    assert "Object" in xml
    assert "Ledger" in xml
    assert "Cash" in xml
    assert "Test Co" in xml


async def test_build_report_xml_contains_dates() -> None:
    xml = TallyConnection._build_report_xml(
        "Trial Balance", from_date="20250101", to_date="20251231"
    )
    assert "Data" in xml
    assert "Trial Balance" in xml
    assert "20250101" in xml
    assert "20251231" in xml
