"""Tests for version detection — version.py."""

from unittest.mock import AsyncMock

from tallybridge.version import TallyProduct, detect_tally_version, parse_version_string


def test_parse_erp9_string() -> None:
    assert parse_version_string("Tally.ERP 9") == TallyProduct.ERP9
    assert parse_version_string("Tally.ERP9") == TallyProduct.ERP9
    assert parse_version_string("erp 9") == TallyProduct.ERP9


def test_parse_prime_baseline() -> None:
    assert parse_version_string("TallyPrime") == TallyProduct.PRIME_1
    assert parse_version_string("TallyPrime 1.0") == TallyProduct.PRIME_1


def test_parse_prime_with_version() -> None:
    assert parse_version_string("TallyPrime 2.0") == TallyProduct.PRIME_2
    assert parse_version_string("TallyPrime 4.0") == TallyProduct.PRIME_4
    assert parse_version_string("TallyPrime 7.0") == TallyProduct.PRIME_7


def test_parse_prime_with_release() -> None:
    assert parse_version_string("TallyPrime Release 4") == TallyProduct.PRIME_4
    assert parse_version_string("TallyPrime Release 6") == TallyProduct.PRIME_6


def test_parse_numeric_only() -> None:
    assert parse_version_string("4.0.1") == TallyProduct.PRIME_4
    assert parse_version_string("7.0") == TallyProduct.PRIME_7
    assert parse_version_string("1.0") == TallyProduct.PRIME_1


def test_parse_empty_or_none() -> None:
    assert parse_version_string("") == TallyProduct.ERP9
    assert parse_version_string(None) == TallyProduct.ERP9
    assert parse_version_string("  ") == TallyProduct.ERP9


def test_parse_unrecognized() -> None:
    assert parse_version_string("SomeRandomString") == TallyProduct.ERP9


def test_product_properties() -> None:
    assert TallyProduct.ERP9.is_erp9 is True
    assert TallyProduct.ERP9.is_prime is False
    assert TallyProduct.PRIME_4.is_prime is True
    assert TallyProduct.PRIME_4.is_erp9 is False
    assert TallyProduct.PRIME_4.supports_connected_gst is True
    assert TallyProduct.PRIME_3.supports_connected_gst is False
    assert TallyProduct.PRIME_6.supports_connected_banking is True
    assert TallyProduct.PRIME_5.supports_connected_banking is False
    assert TallyProduct.PRIME_1.supports_allledger_entries is True
    assert TallyProduct.ERP9.supports_allledger_entries is False


def test_display_name() -> None:
    assert TallyProduct.ERP9.display_name == "Tally.ERP 9"
    assert TallyProduct.PRIME_4.display_name == "TallyPrime 4.x"
    assert TallyProduct.PRIME_7.display_name == "TallyPrime 7.x"


async def test_detect_tally_version_with_version_tag() -> None:
    conn = AsyncMock()
    conn._detected_version = None
    conn.post_xml.return_value = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        "<COMPANY><VERSION>TallyPrime 4.0</VERSION></COMPANY>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    result = await detect_tally_version(conn)
    assert result == TallyProduct.PRIME_4


async def test_detect_tally_version_erp9() -> None:
    conn = AsyncMock()
    conn._detected_version = None
    conn.post_xml.return_value = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        "<COMPANY><VERSION>Tally.ERP 9</VERSION></COMPANY>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    result = await detect_tally_version(conn)
    assert result == TallyProduct.ERP9


async def test_detect_tally_version_no_version_tag() -> None:
    conn = AsyncMock()
    conn._detected_version = None
    conn.post_xml.return_value = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<COMPANY NAME="Test Co"><NAME>Test Co</NAME></COMPANY>'
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    result = await detect_tally_version(conn)
    assert result == TallyProduct.PRIME_1


async def test_detect_tally_version_connection_error() -> None:
    conn = AsyncMock()
    conn._detected_version = None
    conn.post_xml.side_effect = ConnectionError("refused")
    result = await detect_tally_version(conn)
    assert result == TallyProduct.ERP9


async def test_detect_tally_version_caches_result() -> None:
    conn = AsyncMock()
    conn._detected_version = TallyProduct.PRIME_7
    result = await detect_tally_version(conn)
    assert result == TallyProduct.PRIME_7
    conn.post_xml.assert_not_called()


def test_capabilities_erp9() -> None:
    caps = TallyProduct.ERP9.capabilities()
    assert caps["is_prime"] is False
    assert caps["json_api"] is False
    assert caps["base64_encoding"] is False
    assert caps["tally_drive"] is False
    assert caps["connected_gst"] is False


def test_capabilities_prime7() -> None:
    caps = TallyProduct.PRIME_7.capabilities()
    assert caps["is_prime"] is True
    assert caps["json_api"] is True
    assert caps["base64_encoding"] is True
    assert caps["tally_drive"] is True
    assert caps["connected_gst"] is True
    assert caps["connected_banking"] is True


def test_capabilities_prime4() -> None:
    caps = TallyProduct.PRIME_4.capabilities()
    assert caps["connected_gst"] is True
    assert caps["json_api"] is False
    assert caps["tally_drive"] is False


def test_json_api_only_prime7() -> None:
    assert TallyProduct.PRIME_6.supports_json_api is False
    assert TallyProduct.PRIME_7.supports_json_api is True


def test_base64_encoding_only_prime7() -> None:
    assert TallyProduct.PRIME_6.supports_base64_encoding is False
    assert TallyProduct.PRIME_7.supports_base64_encoding is True


def test_parse_prime_release_2() -> None:
    assert parse_version_string("TallyPrime Release 2") == TallyProduct.PRIME_2


def test_parse_prime_release_3() -> None:
    assert parse_version_string("TallyPrime Release 3") == TallyProduct.PRIME_3


def test_parse_prime_release_5() -> None:
    assert parse_version_string("TallyPrime Release 5") == TallyProduct.PRIME_5


def test_parse_prime_release_7() -> None:
    assert parse_version_string("TallyPrime Release 7") == TallyProduct.PRIME_7


def test_parse_numeric_2() -> None:
    assert parse_version_string("2.0") == TallyProduct.PRIME_2


def test_parse_numeric_3() -> None:
    assert parse_version_string("3.0") == TallyProduct.PRIME_3


def test_parse_numeric_5() -> None:
    assert parse_version_string("5.0") == TallyProduct.PRIME_5


def test_parse_numeric_6() -> None:
    assert parse_version_string("6.0") == TallyProduct.PRIME_6


def test_parse_numeric_0_falls_to_erp9() -> None:
    assert parse_version_string("0.5") == TallyProduct.ERP9


def test_capabilities_prime1() -> None:
    caps = TallyProduct.PRIME_1.capabilities()
    assert caps["is_prime"] is True
    assert caps["connected_gst"] is False
    assert caps["connected_banking"] is False
    assert caps["allledger_entries"] is True


def test_capabilities_prime2() -> None:
    caps = TallyProduct.PRIME_2.capabilities()
    assert caps["is_prime"] is True
    assert caps["connected_gst"] is False


def test_capabilities_prime3() -> None:
    caps = TallyProduct.PRIME_3.capabilities()
    assert caps["is_prime"] is True
    assert caps["connected_gst"] is False


def test_capabilities_prime5() -> None:
    caps = TallyProduct.PRIME_5.capabilities()
    assert caps["connected_gst"] is True
    assert caps["connected_banking"] is False


def test_capabilities_prime6() -> None:
    caps = TallyProduct.PRIME_6.capabilities()
    assert caps["connected_banking"] is True
    assert caps["json_api"] is False


def test_display_name_fallback_for_unknown() -> None:
    assert TallyProduct.ERP9.display_name == "Tally.ERP 9"
    assert TallyProduct.PRIME_1.display_name == "TallyPrime 1.x"


async def test_detect_tally_version_no_company_data() -> None:
    conn = AsyncMock()
    conn._detected_version = None
    conn.post_xml.return_value = "<ENVELOPE><BODY><DATA></DATA></BODY></ENVELOPE>"
    result = await detect_tally_version(conn)
    assert result == TallyProduct.ERP9


def test_parse_erp9_variant_patterns() -> None:
    assert parse_version_string("tally erp") == TallyProduct.ERP9
    assert parse_version_string("ERP 9") == TallyProduct.ERP9


def test_supports_tally_drive() -> None:
    assert TallyProduct.PRIME_6.supports_tally_drive is False
    assert TallyProduct.PRIME_7.supports_tally_drive is True


def test_supports_connected_banking() -> None:
    assert TallyProduct.PRIME_5.supports_connected_banking is False
    assert TallyProduct.PRIME_6.supports_connected_banking is True
