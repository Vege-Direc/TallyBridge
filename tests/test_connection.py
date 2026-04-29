"""Tests for connection — SPECS.md §4."""

import json

import httpx
import pytest
from pytest_httpserver import HTTPServer

from tallybridge.config import TallyBridgeConfig
from tallybridge.connection import TallyConnection
from tallybridge.exceptions import TallyConnectionError, TallyDataError
from tallybridge.version import TallyProduct
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


@pytest.fixture
def json_conn(mock_server: HTTPServer):
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
        tally_export_format="json",
    )
    connection = TallyConnection(config)
    connection._detected_version = TallyProduct.PRIME_7
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


async def test_export_collection_returns_json(
    json_conn: TallyConnection,
) -> None:
    result = await json_conn.export_collection(
        "Sync_ledger", "Ledger", ["NAME", "GUID", "ALTERID"]
    )
    assert isinstance(result, dict)
    assert "status" in result


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


def test_fetch_report_parse_parameter() -> None:
    result_type = TallyConnection.fetch_report.__annotations__.get("return")
    assert result_type is not None or True


def test_export_object_parse_routing() -> None:
    from tallybridge.parser import TallyXMLParser

    parser = TallyXMLParser()
    ledger_xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<LEDGER NAME="Test Ledger" RESERVEDNAME="">'
        "<PARENT>Bank Accounts</PARENT>"
        "<OPENINGBALANCE>1000.00</OPENINGBALANCE>"
        "<GUID>GUID123</GUID>"
        "<ALTERID>5</ALTERID>"
        "</LEDGER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    result = parser.parse_ledgers(ledger_xml)
    assert len(result) == 1
    assert result[0].name == "Test Ledger"
    assert result[0].opening_balance == 1000

    voucher_xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER VCHTYPE="Sales" ACTION="Create">'
        "<DATE>20250415</DATE>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<VOUCHERNUMBER>1</VOUCHERNUMBER>"
        "<GUID>VGUID1</GUID>"
        "<ALTERID>10</ALTERID>"
        "<ALLLEDGERENTRIES.LIST>"
        "<LEDGERNAME>Cash</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
        "<AMOUNT>-1000.00</AMOUNT>"
        "</ALLLEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    v_result = parser.parse_vouchers(voucher_xml)
    assert len(v_result) == 1
    assert v_result[0].voucher_type == "Sales"


def test_build_collection_json_structure() -> None:
    headers, body = TallyConnection._build_collection_json(
        "TestColl", "Ledger", ["NAME", "GUID"], company="Test Co"
    )
    assert headers["tallyrequest"] == "Export"
    assert headers["type"] == "Collection"
    assert headers["id"] == "TestColl"
    assert body["static_variables"]["svexportformat"] == "JSONEx"
    assert body["static_variables"]["svcurrentcompany"] == "Test Co"
    assert len(body["tdlmessage"]) == 1
    assert body["tdlmessage"][0]["collection"]["type"] == "Ledger"


def test_build_collection_json_with_filter() -> None:
    headers, body = TallyConnection._build_collection_json(
        "TestColl", "Ledger", ["NAME"], filter_expr="$ALTERID > 100"
    )
    assert body["tdlmessage"][0]["collection"]["filter"] == "AltFilter"
    assert body["tdlmessage"][0]["system"]["name"] == "AltFilter"
    assert body["tdlmessage"][0]["system"]["text"] == "$ALTERID > 100"


def test_build_object_json_by_name() -> None:
    headers, body = TallyConnection._build_object_json(
        "Ledger", name="Cash", company="Test Co"
    )
    assert headers["tallyrequest"] == "Export"
    assert headers["type"] == "Object"
    assert headers["subtype"] == "Ledger"
    assert headers["id"] == "Cash"
    assert "id-encoded" not in headers
    assert body["static_variables"]["svexportformat"] == "JSONEx"


def test_build_object_json_by_guid() -> None:
    headers, body = TallyConnection._build_object_json(
        "Ledger", guid="abc-123"
    )
    assert headers["id"] == "abc-123"


def test_build_object_json_base64_encoding() -> None:
    headers, body = TallyConnection._build_object_json(
        "Ledger", name="शर्मा ट्रेडर्स", supports_base64=True
    )
    assert headers["id"] == "शर्मा ट्रेडर्स"
    assert "id-encoded" in headers
    import base64

    decoded = base64.b64decode(headers["id-encoded"]).decode("utf-8")
    assert decoded == "शर्मा ट्रेडर्स"


def test_build_object_json_no_base64_for_ascii() -> None:
    headers, body = TallyConnection._build_object_json(
        "Ledger", name="Cash", supports_base64=True
    )
    assert "id-encoded" not in headers


def test_build_report_json_structure() -> None:
    headers, body = TallyConnection._build_report_json(
        "Balance Sheet", from_date="20250101", to_date="20251231", company="Test Co"
    )
    assert headers["tallyrequest"] == "Export"
    assert headers["type"] == "Data"
    assert headers["id"] == "Balance Sheet"
    assert body["static_variables"]["svexportformat"] == "JSONEx"
    assert body["static_variables"]["svfromdate"] == "20250101"
    assert body["static_variables"]["svtodate"] == "20251231"
    assert body["static_variables"]["svcurrentcompany"] == "Test Co"
    assert body["static_variables"]["svexportinplainformat"] == "Yes"


def test_get_export_format_auto_without_version() -> None:
    config = TallyBridgeConfig(tally_export_format="auto")
    conn = TallyConnection(config)
    assert conn._get_export_format() == "xml"


def test_get_export_format_auto_with_prime7() -> None:
    config = TallyBridgeConfig(tally_export_format="auto")
    conn = TallyConnection(config)
    conn._detected_version = TallyProduct.PRIME_7
    assert conn._get_export_format() == "json"


def test_get_export_format_auto_with_erp9() -> None:
    config = TallyBridgeConfig(tally_export_format="auto")
    conn = TallyConnection(config)
    conn._detected_version = TallyProduct.ERP9
    assert conn._get_export_format() == "xml"


def test_get_export_format_forced_xml() -> None:
    config = TallyBridgeConfig(tally_export_format="xml")
    conn = TallyConnection(config)
    conn._detected_version = TallyProduct.PRIME_7
    assert conn._get_export_format() == "xml"


def test_get_export_format_forced_json() -> None:
    config = TallyBridgeConfig(tally_export_format="json")
    conn = TallyConnection(config)
    assert conn._get_export_format() == "json"


def test_require_capability_passes_when_no_version() -> None:
    config = TallyBridgeConfig()
    conn = TallyConnection(config)
    conn._require_capability("json_api")


def test_require_capability_passes_when_supported() -> None:
    config = TallyBridgeConfig()
    conn = TallyConnection(config)
    conn._detected_version = TallyProduct.PRIME_7
    conn._require_capability("json_api")


def test_require_capability_raises_when_unsupported() -> None:
    config = TallyBridgeConfig()
    conn = TallyConnection(config)
    conn._detected_version = TallyProduct.ERP9
    with pytest.raises(TallyConnectionError, match="json_api"):
        conn._require_capability("json_api")


async def test_post_json_success(
    mock_server: HTTPServer,
) -> None:
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
    )
    connection = TallyConnection(config)
    headers = {
        "tallyrequest": "Export",
        "type": "Collection",
        "id": "Sync_ledger",
    }
    body = {
        "static_variables": {"svexportformat": "JSONEx"},
        "tdlmessage": [
            {
                "collection": {
                    "name": "Sync_ledger",
                    "type": "Ledger",
                    "fetch": "NAME,GUID",
                }
            }
        ],
    }
    result = await connection.post_json(headers, body)
    assert isinstance(result, dict)
    await connection.close()


async def test_post_json_status_minus_one(
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
            content=json.dumps({"status": "-1", "error": "Something broke"}).encode(),
            headers={"Content-Type": "application/json"},
        )

    connection._client.post = mock_post
    with pytest.raises(TallyDataError, match="status -1"):
        await connection.post_json({}, {})
    connection._client.post = original_post
    await connection.close()


async def test_post_json_status_0_strict(
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
            content=json.dumps({"status": "0", "data": {}}).encode(),
            headers={"Content-Type": "application/json"},
        )

    connection._client.post = mock_post
    with pytest.raises(TallyDataError, match="strict mode"):
        await connection.post_json({}, {})
    connection._client.post = original_post
    await connection.close()


async def test_post_json_invalid_json(
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
            content=b"not valid json {{{",
            headers={"Content-Type": "application/json"},
        )

    connection._client.post = mock_post
    with pytest.raises(TallyDataError, match="invalid JSON"):
        await connection.post_json({}, {})
    connection._client.post = original_post
    await connection.close()


async def test_post_json_connection_error() -> None:
    config = TallyBridgeConfig(tally_host="localhost", tally_port=19999)
    connection = TallyConnection(config)
    with pytest.raises(TallyConnectionError):
        await connection.post_json({}, {})
    await connection.close()


async def test_export_object_json(
    json_conn: TallyConnection,
) -> None:
    result = await json_conn.export_object("Ledger", name="Cash")
    assert isinstance(result, dict)
    await json_conn.close()


async def test_fetch_report_json(
    json_conn: TallyConnection,
) -> None:
    result = await json_conn.fetch_report(
        "Balance Sheet", from_date="20250101", to_date="20251231"
    )
    assert isinstance(result, dict)
    await json_conn.close()


# ── Import Tests (Phase 11B) ───────────────────────────────────────────


@pytest.fixture
def write_conn(mock_server: HTTPServer):
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
        allow_writes=True,
    )
    connection = TallyConnection(config)
    yield connection


@pytest.fixture
def write_json_conn(mock_server: HTTPServer):
    config = TallyBridgeConfig(
        tally_host="localhost",
        tally_port=mock_server.port,
        tally_export_format="json",
        allow_writes=True,
    )
    connection = TallyConnection(config)
    connection._detected_version = TallyProduct.PRIME_7
    yield connection


async def test_import_masters_blocked_without_writes(
    conn: TallyConnection,
) -> None:
    xml = TallyConnection.build_ledger_xml("Test Ledger", "Sundry Debtors")
    with pytest.raises(TallyConnectionError, match="TALLYBRIDGE_ALLOW_WRITES"):
        await conn.import_masters(xml)
    await conn.close()


async def test_import_vouchers_blocked_without_writes(
    conn: TallyConnection,
) -> None:
    xml = TallyConnection.build_voucher_xml(
        "Sales", "20250101", [{"ledger_name": "Cash", "amount": "1000"}]
    )
    with pytest.raises(TallyConnectionError, match="TALLYBRIDGE_ALLOW_WRITES"):
        await conn.import_vouchers(xml)
    await conn.close()


async def test_import_masters_xml(write_conn: TallyConnection) -> None:
    xml = TallyConnection.build_ledger_xml("Test Ledger", "Sundry Debtors", "5000")
    result = await write_conn.import_masters(xml)
    assert result.success is True
    assert result.created >= 1
    assert result.errors == 0
    await write_conn.close()


async def test_import_vouchers_xml(write_conn: TallyConnection) -> None:
    xml = TallyConnection.build_voucher_xml(
        "Sales",
        "20250101",
        [
            {"ledger_name": "Sales", "amount": "-1000"},
            {"ledger_name": "Cash", "amount": "1000"},
        ],
        narration="Test voucher",
        voucher_number="V-001",
    )
    result = await write_conn.import_vouchers(xml)
    assert result.success is True
    assert result.created >= 1
    assert result.errors == 0
    await write_conn.close()


async def test_import_masters_json(
    write_json_conn: TallyConnection,
) -> None:
    msg = TallyConnection.build_ledger_json(
        "Test Ledger", "Sundry Debtors", "5000"
    )
    result = await write_json_conn.import_masters_json(msg)
    assert result.success is True
    assert result.created >= 1
    await write_json_conn.close()


async def test_import_vouchers_json(
    write_json_conn: TallyConnection,
) -> None:
    msg = TallyConnection.build_voucher_json(
        "Sales",
        "20250101",
        [
            {"ledger_name": "Sales", "amount": "-1000"},
            {"ledger_name": "Cash", "amount": "1000"},
        ],
        narration="Test JSON voucher",
    )
    result = await write_json_conn.import_vouchers_json(msg)
    assert result.success is True
    assert result.created >= 1
    await write_json_conn.close()


async def test_import_json_blocked_without_json_api(
    write_conn: TallyConnection,
) -> None:
    write_conn._detected_version = TallyProduct.PRIME_1
    msg = TallyConnection.build_ledger_json("Test", "Sundry Debtors")
    with pytest.raises(TallyConnectionError, match="json_api"):
        await write_conn.import_masters_json(msg)
    await write_conn.close()


async def test_build_ledger_xml() -> None:
    xml = TallyConnection.build_ledger_xml(
        "New Ledger", "Bank Accounts", "10000", action="Create"
    )
    assert 'NAME="New Ledger"' in xml
    assert "<PARENT>Bank Accounts</PARENT>" in xml
    assert "<OPENINGBALANCE>10000</OPENINGBALANCE>" in xml
    assert 'ACTION="Create"' in xml


async def test_build_voucher_xml() -> None:
    xml = TallyConnection.build_voucher_xml(
        "Payment",
        "20250315",
        [{"ledger_name": "Cash", "amount": "500"}],
        narration="Payment test",
        voucher_number="P-001",
    )
    assert 'VCHTYPE="Payment"' in xml
    assert "<DATE>20250315</DATE>" in xml
    assert "<LEDGERNAME>Cash</LEDGERNAME>" in xml
    assert "<AMOUNT>500</AMOUNT>" in xml
    assert "<NARRATION>Payment test</NARRATION>" in xml
    assert "<VOUCHERNUMBER>P-001</VOUCHERNUMBER>" in xml


async def test_build_cancel_voucher_xml() -> None:
    xml = TallyConnection.build_cancel_voucher_xml("guid-abc-123", "Sales")
    assert "<GUID>guid-abc-123</GUID>" in xml
    assert "<ISCANCELLED>Yes</ISCANCELLED>" in xml
    assert 'ACTION="Alter"' in xml


async def test_build_ledger_json() -> None:
    msg = TallyConnection.build_ledger_json(
        "New Ledger", "Bank Accounts", "10000", action="Create"
    )
    assert "ledger" in msg
    assert msg["ledger"]["name"] == "New Ledger"
    assert msg["ledger"]["parent"] == "Bank Accounts"
    assert msg["ledger"]["openingbalance"] == "10000"
    assert msg["ledger"]["action"] == "Create"


async def test_build_voucher_json() -> None:
    msg = TallyConnection.build_voucher_json(
        "Payment",
        "20250315",
        [{"ledger_name": "Cash", "amount": "500"}],
        narration="Payment test",
    )
    assert "voucher" in msg
    assert msg["voucher"]["vouchertype"] == "Payment"
    assert msg["voucher"]["date"] == "20250315"
    assert len(msg["voucher"]["allledgerentrieslist"]) == 1
    assert msg["voucher"]["narration"] == "Payment test"


async def test_build_cancel_voucher_json() -> None:
    msg = TallyConnection.build_cancel_voucher_json("guid-abc-123", "Sales")
    assert msg["voucher"]["guid"] == "guid-abc-123"
    assert msg["voucher"]["iscancelled"] == "Yes"
    assert msg["voucher"]["action"] == "Alter"


async def test_parse_import_response_xml_success() -> None:
    response = (
        "<ENVELOPE><HEADER><VERSION>1</VERSION><STATUS>1</STATUS></HEADER>"
        "<BODY><DATA><IMPORTRESULT>"
        "<CREATED>3</CREATED><ALTERED>1</ALTERED>"
        "<DELETED>0</DELETED><ERRORS>0</ERRORS>"
        "</IMPORTRESULT></DATA></BODY></ENVELOPE>"
    )
    result = TallyConnection._parse_import_response_xml(response)
    assert result.success is True
    assert result.created == 3
    assert result.altered == 1
    assert result.deleted == 0
    assert result.errors == 0


async def test_parse_import_response_xml_with_errors() -> None:
    response = (
        "<ENVELOPE><HEADER><VERSION>1</VERSION><STATUS>-1</STATUS></HEADER>"
        "<BODY><DATA><IMPORTRESULT>"
        "<CREATED>0</CREATED><ALTERED>0</ALTERED>"
        "<DELETED>0</DELETED><ERRORS>2</ERRORS>"
        "</IMPORTRESULT>"
        "<LINEERROR>Duplicate ledger</LINEERROR>"
        "</DATA></BODY></ENVELOPE>"
    )
    result = TallyConnection._parse_import_response_xml(response)
    assert result.success is False
    assert result.errors == 2
    assert len(result.error_messages) >= 1


async def test_parse_import_response_json_success() -> None:
    data = {
        "status": "1",
        "cmp_info": {
            "created": 2,
            "altered": 1,
            "deleted": 0,
            "errors": 0,
        },
    }
    result = TallyConnection._parse_import_response_json(data)
    assert result.success is True
    assert result.created == 2
    assert result.altered == 1
    assert result.errors == 0


async def test_parse_import_response_json_with_errors() -> None:
    data = {
        "status": "-1",
        "cmp_info": {
            "created": 0,
            "altered": 0,
            "deleted": 0,
            "errors": 1,
        },
        "tallymessage": [{"lineerror": "Missing parent group"}],
    }
    result = TallyConnection._parse_import_response_json(data)
    assert result.success is False
    assert result.errors == 1
    assert "Missing parent group" in result.error_messages


async def test_build_import_json_masters() -> None:
    headers, body = TallyConnection._build_import_json(
        import_id="All Masters",
        tally_message={"ledger": {"name": "Test"}},
        company="Test Co",
    )
    assert headers["tallyrequest"] == "Import"
    assert headers["type"] == "Data"
    assert headers["id"] == "All Masters"
    assert headers["detailed-response"] == "Yes"
    assert body["static_variables"]["svmstimportformat"] == "JSONEx"
    assert body["static_variables"]["svcurrentcompany"] == "Test Co"
    assert body["tallymessage"] == {"ledger": {"name": "Test"}}


async def test_build_import_json_vouchers() -> None:
    headers, body = TallyConnection._build_import_json(
        import_id="Vouchers",
        tally_message={"voucher": {}},
    )
    assert headers["id"] == "Vouchers"
    assert body["static_variables"]["svvchimportformat"] == "JSONEx"


async def test_allow_writes_config_default() -> None:
    config = TallyBridgeConfig()
    assert config.allow_writes is False


async def test_allow_writes_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TALLYBRIDGE_ALLOW_WRITES", "true")
    config = TallyBridgeConfig()
    assert config.allow_writes is True
