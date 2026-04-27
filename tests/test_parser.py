"""Tests for parser — SPECS.md §5."""

from datetime import date
from decimal import Decimal

from tallybridge.parser import TallyXMLParser
from tests.mock_tally import (
    build_cost_center_xml,
    build_group_xml,
    build_ledger_xml,
    build_stock_group_xml,
    build_stock_item_xml,
    build_unit_xml,
    build_voucher_type_xml,
    build_voucher_xml,
    build_voucher_xml_all_ledger,
)

parser = TallyXMLParser()


def test_parse_amount_dr() -> None:
    assert parser.parse_amount("1234.56 Dr") == Decimal("1234.56")


def test_parse_amount_cr() -> None:
    assert parser.parse_amount("1234.56 Cr") == Decimal("-1234.56")


def test_parse_amount_negative() -> None:
    assert parser.parse_amount("-500.00") == Decimal("-500.00")


def test_parse_amount_empty() -> None:
    assert parser.parse_amount("") == Decimal("0")


def test_parse_amount_none() -> None:
    assert parser.parse_amount(None) == Decimal("0")


def test_parse_amount_invalid() -> None:
    assert parser.parse_amount("not_a_number") == Decimal("0")


def test_parse_date_valid() -> None:
    assert parser.parse_date("20250415") == date(2025, 4, 15)


def test_parse_date_empty() -> None:
    assert parser.parse_date("") is None


def test_parse_date_none() -> None:
    assert parser.parse_date(None) is None


def test_parse_date_invalid() -> None:
    assert parser.parse_date("not_a_date") is None


def test_parse_date_short() -> None:
    assert parser.parse_date("2025") is None


def test_parse_bool_yes() -> None:
    assert parser.parse_bool("Yes") is True


def test_parse_bool_no() -> None:
    assert parser.parse_bool("No") is False


def test_parse_bool_none() -> None:
    assert parser.parse_bool(None) is False


def test_parse_ledgers() -> None:
    xml = build_ledger_xml()
    ledgers = parser.parse_ledgers(xml)
    assert len(ledgers) >= 3
    cash = [ledger for ledger in ledgers if ledger.name == "Cash"][0]
    assert cash.parent_group == "Cash-in-Hand"
    assert cash.closing_balance == Decimal("45000")


def test_parse_ledgers_unicode() -> None:
    xml = build_ledger_xml()
    ledgers = parser.parse_ledgers(xml)
    hindi = [ledger for ledger in ledgers if "शर्मा" in ledger.name]
    assert len(hindi) >= 1


def test_parse_vouchers_with_ledger_entries() -> None:
    xml = build_voucher_xml()
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) >= 1
    v = vouchers[0]
    assert len(v.ledger_entries) >= 2


def test_parse_vouchers_cancelled() -> None:
    xml = build_voucher_xml()
    vouchers = parser.parse_vouchers(xml)
    cancelled = [v for v in vouchers if v.is_cancelled]
    assert len(cancelled) >= 1
    assert cancelled[0].is_cancelled is True


def test_parse_groups() -> None:
    xml = build_group_xml()
    groups = parser.parse_groups(xml)
    assert len(groups) >= 3


def test_parse_stock_items() -> None:
    xml = build_stock_item_xml()
    items = parser.parse_stock_items(xml)
    assert len(items) >= 3
    widget_a = [i for i in items if i.name == "Widget A"][0]
    assert widget_a.unit == "Nos"


def test_parse_units() -> None:
    xml = build_unit_xml()
    units = parser.parse_units(xml)
    assert len(units) >= 4


def test_parse_stock_groups() -> None:
    xml = build_stock_group_xml()
    groups = parser.parse_stock_groups(xml)
    assert len(groups) >= 2


def test_parse_cost_centers() -> None:
    xml = build_cost_center_xml()
    centers = parser.parse_cost_centers(xml)
    assert len(centers) >= 3


def test_parse_malformed_xml_returns_empty() -> None:
    assert parser.parse_ledgers("not xml at all") == []
    assert parser.parse_groups("not xml at all") == []
    assert parser.parse_vouchers("not xml at all") == []
    assert parser.parse_stock_items("not xml at all") == []


def test_get_text_attribute_path() -> None:
    import xml.etree.ElementTree as ET

    elem = ET.fromstring('<LEDGER NAME="AttrValue"><NAME>ChildValue</NAME></LEDGER>')
    assert parser.get_text(elem, "NAME") == "ChildValue"
    assert parser.get_text(elem, "NAME_ATTR_ONLY") == ""
    elem_no_child = ET.fromstring('<LEDGER ONLYATTR="AttrVal"/>')
    assert parser.get_text(elem_no_child, "ONLYATTR") == "AttrVal"


def test_get_text_none_element() -> None:
    assert parser.get_text(None, "NAME") == ""
    assert parser.get_text(None, "NAME", "default") == "default"


def test_get_text_child_no_text() -> None:
    import xml.etree.ElementTree as ET

    elem = ET.fromstring("<LEDGER><EMPTY/></LEDGER>")
    assert parser.get_text(elem, "EMPTY") == ""


def test_parse_voucher_types() -> None:
    xml = build_voucher_type_xml()
    vtypes = parser.parse_voucher_types(xml)
    assert len(vtypes) >= 4
    sales = [vt for vt in vtypes if vt.name == "Sales"][0]
    assert sales.parent == "Accounting Vouchers"


def test_parse_voucher_types_malformed() -> None:
    assert parser.parse_voucher_types("not xml") == []


def test_parse_vouchers_with_inventory() -> None:
    xml = build_voucher_xml()
    vouchers = parser.parse_vouchers(xml)
    with_inv = [v for v in vouchers if len(v.inventory_entries) > 0]
    assert len(with_inv) >= 1
    inv = with_inv[0].inventory_entries[0]
    assert inv.stock_item_name == "Widget A"


def test_parse_vouchers_with_gst() -> None:
    xml = build_voucher_xml()
    vouchers = parser.parse_vouchers(xml)
    sales_vouchers = [v for v in vouchers if v.voucher_type == "Sales"]
    assert len(sales_vouchers) >= 1
    for sv in sales_vouchers:
        if sv.gst_amount > 0:
            assert sv.gst_amount > Decimal("0")


def test_parse_voucher_with_unparseable_date_is_skipped() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="skip-date-guid" VCHTYPE="Sales">'
        "<ALTERID>100</ALTERID>"
        "<DATE>INVALID</DATE>"
        "<VOUCHERNUMBER>SI/BAD</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Cash</LEDGERNAME>"
        "<AMOUNT>100.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 0


def test_parse_outstanding_bill_with_unparseable_date_is_skipped() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<BILL PARTYNAME="Test">'
        "<DATE>INVALID</DATE>"
        "<BILLNUMBER>INV001</BILLNUMBER>"
        "<BILLAMOUNT>5000.00</BILLAMOUNT>"
        "<OUTSTANDINGAMOUNT>3000.00</OUTSTANDINGAMOUNT>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "</BILL>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    bills = parser.parse_outstanding_bills(xml)
    assert len(bills) == 0


def test_parse_voucher_with_all_fields() -> None:
    xml = build_voucher_xml()
    vouchers = parser.parse_vouchers(xml)
    v = vouchers[0]
    assert v.voucher_type in ("Sales", "Purchase", "Payment")
    assert v.date is not None


def test_parse_quantity_valid() -> None:
    assert TallyXMLParser.parse_quantity("5 Nos") == Decimal("5")
    assert TallyXMLParser.parse_quantity("-10 Kgs") == Decimal("-10")


def test_parse_quantity_empty() -> None:
    assert TallyXMLParser.parse_quantity("") == Decimal("0")
    assert TallyXMLParser.parse_quantity(None) == Decimal("0")


def test_parse_quantity_invalid() -> None:
    assert TallyXMLParser.parse_quantity("abc Nos") == Decimal("0")


def test_parse_rate_valid() -> None:
    assert TallyXMLParser.parse_rate("15000.00/Nos") == Decimal("15000.00")


def test_parse_rate_empty() -> None:
    assert TallyXMLParser.parse_rate("") == Decimal("0")
    assert TallyXMLParser.parse_rate(None) == Decimal("0")


def test_parse_rate_invalid() -> None:
    assert TallyXMLParser.parse_rate("abc/Nos") == Decimal("0")


def test_parse_units_malformed() -> None:
    assert parser.parse_units("not xml") == []


def test_parse_stock_groups_malformed() -> None:
    assert parser.parse_stock_groups("not xml") == []


def test_parse_cost_centers_malformed() -> None:
    assert parser.parse_cost_centers("not xml") == []


def test_parse_stock_items_malformed() -> None:
    assert parser.parse_stock_items("not xml") == []


def test_parse_outstanding_bills_malformed() -> None:
    assert parser.parse_outstanding_bills("not xml") == []


def test_parse_outstanding_bills() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<BILL PARTYNAME="Test"><DATE>20250415</DATE>'
        "<BILLNUMBER>INV001</BILLNUMBER>"
        "<BILLAMOUNT>5000.00</BILLAMOUNT>"
        "<OUTSTANDINGAMOUNT>3000.00</OUTSTANDINGAMOUNT>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "</BILL>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    bills = parser.parse_outstanding_bills(xml)
    assert len(bills) >= 1
    assert bills[0].party_name == "Test"
    assert bills[0].bill_amount == Decimal("5000.00")


def test_parse_voucher_with_bill_allocations() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="test-guid-001" VCHTYPE="Sales">'
        "<ALTERID>100</ALTERID>"
        "<DATE>20250401</DATE>"
        "<EFFECTIVEDATE>20250401</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>SI/001</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Sharma Trading Co</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
        "<AMOUNT>50000.00</AMOUNT>"
        "<BILLALLOCATIONS.LIST>"
        "<BILLTYPE>New Ref</BILLTYPE>"
        "<NAME>SI/001</NAME>"
        "<AMOUNT>50000.00</AMOUNT>"
        "<BILLCREDITPERIOD>"
        "<INDAYS>30</INDAYS>"
        "<INTEXT>30 Days</INTEXT>"
        "</BILLCREDITPERIOD>"
        "</BILLALLOCATIONS.LIST>"
        "</LEDGERENTRIES.LIST>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Sales</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
        "<AMOUNT>-50000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1
    v = vouchers[0]
    assert len(v.bill_allocations) == 1
    ba = v.bill_allocations[0]
    assert ba.ledger_name == "Sharma Trading Co"
    assert ba.bill_name == "SI/001"
    assert ba.amount == Decimal("50000.00")
    assert ba.bill_type == "New Ref"
    assert ba.bill_credit_period == 30


def test_parse_voucher_with_cost_centre_allocations() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="test-guid-002" VCHTYPE="Purchase">'
        "<ALTERID>101</ALTERID>"
        "<DATE>20250403</DATE>"
        "<EFFECTIVEDATE>20250403</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>PI/001</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Mehta Suppliers</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
        "<AMOUNT>-42000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Purchase</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
        "<AMOUNT>42000.00</AMOUNT>"
        "<COSTCENTRE.LIST>"
        "<COSTCENTRENAME>Head Office</COSTCENTRENAME>"
        "<AMOUNT>42000.00</AMOUNT>"
        "</COSTCENTRE.LIST>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1
    v = vouchers[0]
    assert len(v.cost_centre_allocations) == 1
    cc = v.cost_centre_allocations[0]
    assert cc.ledger_name == "Purchase"
    assert cc.cost_centre == "Head Office"
    assert cc.amount == Decimal("42000.00")


def test_parse_voucher_with_category_allocations() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="test-guid-003" VCHTYPE="Journal">'
        "<ALTERID>102</ALTERID>"
        "<DATE>20250405</DATE>"
        "<EFFECTIVEDATE>20250405</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>JR/001</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Journal</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Petrol Expenses</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
        "<AMOUNT>2640.00</AMOUNT>"
        "<CATEGORYALLOCATIONS.LIST>"
        "<CATEGORY>Primary Cost Category</CATEGORY>"
        "<COSTCENTRE.LIST>"
        "<COSTCENTRENAME>Branch A</COSTCENTRENAME>"
        "<AMOUNT>2640.00</AMOUNT>"
        "</COSTCENTRE.LIST>"
        "</CATEGORYALLOCATIONS.LIST>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1
    v = vouchers[0]
    assert len(v.cost_centre_allocations) == 1
    cc = v.cost_centre_allocations[0]
    assert cc.cost_centre == "Branch A"
    assert cc.amount == Decimal("2640.00")


def test_parse_voucher_bill_allocation_without_credit_period() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="test-guid-004" VCHTYPE="Payment">'
        "<ALTERID>103</ALTERID>"
        "<DATE>20250408</DATE>"
        "<EFFECTIVEDATE>20250408</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>PMT/001</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Payment</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Sharma Trading Co</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
        "<AMOUNT>20000.00</AMOUNT>"
        "<BILLALLOCATIONS.LIST>"
        "<BILLTYPE>On Account</BILLTYPE>"
        "<AMOUNT>20000.00</AMOUNT>"
        "</BILLALLOCATIONS.LIST>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1
    v = vouchers[0]
    assert len(v.bill_allocations) == 1
    ba = v.bill_allocations[0]
    assert ba.bill_type == "On Account"
    assert ba.bill_name == ""
    assert ba.bill_credit_period is None


def test_parse_voucher_with_allledger_entries_list() -> None:
    xml = build_voucher_xml_all_ledger()
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) >= 1
    v = vouchers[0]
    assert len(v.ledger_entries) >= 4
    ledger_names = [e.ledger_name for e in v.ledger_entries]
    assert "Sharma Trading Co" in ledger_names
    assert "Sales" in ledger_names
    assert "CGST" in ledger_names
    assert "SGST" in ledger_names


def test_parse_voucher_with_allinventory_entries_list() -> None:
    xml = build_voucher_xml_all_ledger()
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) >= 1
    v = vouchers[0]
    assert len(v.inventory_entries) >= 1
    assert v.inventory_entries[0].stock_item_name == "Widget A"


def test_parse_voucher_allledger_with_bill_allocations() -> None:
    xml = build_voucher_xml_all_ledger()
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) >= 1
    v = vouchers[0]
    assert len(v.bill_allocations) >= 1
    ba = v.bill_allocations[0]
    assert ba.bill_credit_period == 45
    assert ba.bill_type == "New Ref"


def test_parse_bill_credit_period_dueondate_fallback() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="test-guid-due" VCHTYPE="Sales">'
        "<ALTERID>200</ALTERID>"
        "<DATE>20250401</DATE>"
        "<EFFECTIVEDATE>20250401</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>SI/DUE/001</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Sharma Trading Co</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
        "<AMOUNT>50000.00</AMOUNT>"
        "<BILLALLOCATIONS.LIST>"
        "<BILLTYPE>New Ref</BILLTYPE>"
        "<NAME>SI/DUE/001</NAME>"
        "<AMOUNT>50000.00</AMOUNT>"
        "<BILLDATE>20250401</BILLDATE>"
        "<BILLCREDITPERIOD>"
        "<DUEONDATE>20250501</DUEONDATE>"
        "</BILLCREDITPERIOD>"
        "</BILLALLOCATIONS.LIST>"
        "</LEDGERENTRIES.LIST>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Sales</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
        "<AMOUNT>-50000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1
    ba = vouchers[0].bill_allocations[0]
    assert ba.bill_credit_period == 30
