"""Tests for parser — SPECS.md §5."""

from datetime import date
from decimal import Decimal

from tallybridge.parser import TallyJSONParser, TallyXMLParser
from tests.mock_tally import (
    SAMPLE_COST_CENTERS_JSON,
    SAMPLE_GROUPS_JSON,
    SAMPLE_LEDGERS_JSON,
    SAMPLE_STOCK_GROUPS_JSON,
    SAMPLE_STOCK_ITEMS_JSON,
    SAMPLE_UNITS_JSON,
    SAMPLE_VOUCHER_TYPES_JSON,
    SAMPLE_VOUCHERS_JSON,
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


def test_parse_ledger_element_exception() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<LEDGER NAME="Bad Ledger"><GUID>g1</GUID>'
        "<ALTERID>not_a_number</ALTERID>"
        "</LEDGER>"
        '<LEDGER NAME="Good Ledger"><GUID>g2</GUID>'
        "<ALTERID>10</ALTERID><NAME>Good Ledger</NAME>"
        "<PARENT>Cash-in-Hand</PARENT>"
        "<OPENINGBALANCE>0</OPENINGBALANCE>"
        "<CLOSINGBALANCE>100</CLOSINGBALANCE>"
        "<ISREVENUE>No</ISREVENUE>"
        "<AFFECTSGROSSPROFIT>No</AFFECTSGROSSPROFIT>"
        "</LEDGER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    ledgers = parser.parse_ledgers(xml)
    assert len(ledgers) == 1
    assert ledgers[0].name == "Good Ledger"


def test_parse_group_element_exception() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<GROUP NAME="Bad Group"><GUID>g1</GUID>'
        "<ALTERID>not_a_number</ALTERID>"
        "</GROUP>"
        '<GROUP NAME="Good Group"><GUID>g2</GUID>'
        "<ALTERID>10</ALTERID><NAME>Good Group</NAME>"
        "<PARENT>Primary</PARENT>"
        "<PRIMARYGROUP>Yes</PRIMARYGROUP>"
        "<ISREVENUE>No</ISREVENUE>"
        "<AFFECTSGROSSPROFIT>No</AFFECTSGROSSPROFIT>"
        "<NETDEBITCREDIT>Dr</NETDEBITCREDIT>"
        "</GROUP>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    groups = parser.parse_groups(xml)
    assert len(groups) == 1
    assert groups[0].name == "Good Group"


def test_parse_stock_item_element_exception() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<STOCKITEM NAME="Bad Item"><GUID>g1</GUID>'
        "<ALTERID>not_a_number</ALTERID>"
        "</STOCKITEM>"
        '<STOCKITEM NAME="Good Item"><GUID>g2</GUID>'
        "<ALTERID>10</ALTERID><NAME>Good Item</NAME>"
        "<PARENT>Widgets</PARENT>"
        "<BASEUNITS>Nos</BASEUNITS>"
        "<CLOSINGBALANCE>5 Nos</CLOSINGBALANCE>"
        "<CLOSINGVALUE>500.00</CLOSINGVALUE>"
        "</STOCKITEM>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    items = parser.parse_stock_items(xml)
    assert len(items) == 1
    assert items[0].name == "Good Item"


def test_parse_voucher_type_element_exception() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHERTYPE NAME="Bad"><GUID>g1</GUID>'
        "<ALTERID>not_a_number</ALTERID>"
        "</VOUCHERTYPE>"
        '<VOUCHERTYPE NAME="Good"><GUID>g2</GUID>'
        "<ALTERID>10</ALTERID><NAME>Good</NAME>"
        "<PARENT>Accounting Vouchers</PARENT>"
        "</VOUCHERTYPE>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vtypes = parser.parse_voucher_types(xml)
    assert len(vtypes) == 1
    assert vtypes[0].name == "Good"


def test_parse_unit_element_exception() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<UNIT NAME="Bad"><GUID>g1</GUID>'
        "<ALTERID>not_a_number</ALTERID>"
        "</UNIT>"
        '<UNIT NAME="Good"><GUID>g2</GUID>'
        "<ALTERID>10</ALTERID><NAME>Good</NAME>"
        "<UNITTYPE>Simple</UNITTYPE>"
        "<DECIMALPLACES>2</DECIMALPLACES>"
        "</UNIT>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    units = parser.parse_units(xml)
    assert len(units) == 1
    assert units[0].name == "Good"


def test_parse_stock_group_element_exception() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<STOCKGROUP NAME="Bad"><GUID>g1</GUID>'
        "<ALTERID>not_a_number</ALTERID>"
        "</STOCKGROUP>"
        '<STOCKGROUP NAME="Good"><GUID>g2</GUID>'
        "<ALTERID>10</ALTERID><NAME>Good</NAME>"
        "<PARENT>Primary</PARENT>"
        "<SHOULDQUANTITIESADD>Yes</SHOULDQUANTITIESADD>"
        "</STOCKGROUP>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    groups = parser.parse_stock_groups(xml)
    assert len(groups) == 1
    assert groups[0].name == "Good"


def test_parse_cost_center_element_exception() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<COSTCENTRE NAME="Bad"><GUID>g1</GUID>'
        "<ALTERID>not_a_number</ALTERID>"
        "</COSTCENTRE>"
        '<COSTCENTRE NAME="Good"><GUID>g2</GUID>'
        "<ALTERID>10</ALTERID><NAME>Good</NAME>"
        "<PARENT>Primary</PARENT>"
        "<COSTCENTRETYPE>Primary</COSTCENTRETYPE>"
        "</COSTCENTRE>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    centers = parser.parse_cost_centers(xml)
    assert len(centers) == 1
    assert centers[0].name == "Good"


def test_parse_voucher_element_exception() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="bad-guid" VCHTYPE="Sales">'
        "<ALTERID>not_a_number</ALTERID>"
        "<DATE>20250401</DATE>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "</VOUCHER>"
        '<VOUCHER GUID="good-guid" VCHTYPE="Sales">'
        "<ALTERID>100</ALTERID>"
        "<DATE>20250401</DATE>"
        "<VOUCHERNUMBER>SI/001</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Cash</LEDGERNAME>"
        "<AMOUNT>1000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1
    assert vouchers[0].guid == "good-guid"


def test_parse_bill_element_exception() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<BILL PARTYNAME="Bad Bill"><DATE>20250415</DATE>'
        "<BILLAMOUNT>5000.00</BILLAMOUNT>"
        "<OUTSTANDINGAMOUNT>3000.00</OUTSTANDINGAMOUNT>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "</BILL>"
        '<BILL PARTYNAME="Good Bill"><DATE>20250415</DATE>'
        "<BILLNUMBER>INV002</BILLNUMBER>"
        "<BILLAMOUNT>5000.00</BILLAMOUNT>"
        "<OUTSTANDINGAMOUNT>3000.00</OUTSTANDINGAMOUNT>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "</BILL>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    bills = parser.parse_outstanding_bills(xml)
    assert len(bills) == 2
    assert bills[1].party_name == "Good Bill"


def test_parse_complex_amount_inner_amount() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="complex-amt-guid" VCHTYPE="Sales">'
        "<ALTERID>100</ALTERID>"
        "<DATE>20250401</DATE>"
        "<EFFECTIVEDATE>20250401</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>SI/COMP</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Cash</LEDGERNAME>"
        "<AMOUNT><AMOUNT>0</AMOUNT><ISDEBIT>True</ISDEBIT></AMOUNT>"
        "<BILLALLOCATIONS.LIST>"
        "<BILLTYPE>New Ref</BILLTYPE>"
        "<NAME>SI/COMP</NAME>"
        "<AMOUNT><AMOUNT>0</AMOUNT><ISDEBIT>True</ISDEBIT></AMOUNT>"
        "<BILLCREDITPERIOD>"
        "<INDAYS>30</INDAYS>"
        "</BILLCREDITPERIOD>"
        "</BILLALLOCATIONS.LIST>"
        "</LEDGERENTRIES.LIST>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Sales</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
        "<AMOUNT>-5000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1


def test_parse_voucher_erp9_ledger_entries_fallback() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="erp9-guid" VCHTYPE="Sales">'
        "<ALTERID>50</ALTERID>"
        "<DATE>20250401</DATE>"
        "<EFFECTIVEDATE>20250401</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>SI/ERP9</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Debtor A</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
        "<AMOUNT>20000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Sales</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
        "<AMOUNT>-20000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1
    assert len(vouchers[0].ledger_entries) == 2


def test_parse_voucher_erp9_inventory_entries_fallback() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="erp9-inv-guid" VCHTYPE="Sales">'
        "<ALTERID>51</ALTERID>"
        "<DATE>20250402</DATE>"
        "<EFFECTIVEDATE>20250402</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>SI/ERP9INV</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Debtor B</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
        "<AMOUNT>15000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "<INVENTORYENTRIES.LIST>"
        "<STOCKITEMNAME>Widget X</STOCKITEMNAME>"
        "<ACTUALQTY>10 Nos</ACTUALQTY>"
        "<RATE>1500.00/Nos</RATE>"
        "<AMOUNT>15000.00</AMOUNT>"
        "</INVENTORYENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1
    assert len(vouchers[0].inventory_entries) == 1
    assert vouchers[0].inventory_entries[0].stock_item_name == "Widget X"


def test_parse_bill_credit_period_text_only() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="bcp-text-guid" VCHTYPE="Sales">'
        "<ALTERID>201</ALTERID>"
        "<DATE>20250401</DATE>"
        "<EFFECTIVEDATE>20250401</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>SI/BCP</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Party A</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
        "<AMOUNT>10000.00</AMOUNT>"
        "<BILLALLOCATIONS.LIST>"
        "<BILLTYPE>New Ref</BILLTYPE>"
        "<NAME>SI/BCP</NAME>"
        "<AMOUNT>10000.00</AMOUNT>"
        "<BILLCREDITPERIOD>45</BILLCREDITPERIOD>"
        "</BILLALLOCATIONS.LIST>"
        "</LEDGERENTRIES.LIST>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Sales</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
        "<AMOUNT>-10000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1
    assert vouchers[0].bill_allocations[0].bill_credit_period == 45


def test_parse_bill_credit_period_invalid_text() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="bcp-invalid-guid" VCHTYPE="Sales">'
        "<ALTERID>202</ALTERID>"
        "<DATE>20250401</DATE>"
        "<EFFECTIVEDATE>20250401</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>SI/BCPINV</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Party B</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
        "<AMOUNT>8000.00</AMOUNT>"
        "<BILLALLOCATIONS.LIST>"
        "<BILLTYPE>New Ref</BILLTYPE>"
        "<NAME>SI/BCPINV</NAME>"
        "<AMOUNT>8000.00</AMOUNT>"
        "<BILLCREDITPERIOD>not_a_number</BILLCREDITPERIOD>"
        "</BILLALLOCATIONS.LIST>"
        "</LEDGERENTRIES.LIST>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Sales</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
        "<AMOUNT>-8000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1
    assert vouchers[0].bill_allocations[0].bill_credit_period is None


def test_parse_bill_credit_period_no_bill_date_for_diff() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="bcp-nodate-guid" VCHTYPE="Sales">'
        "<ALTERID>203</ALTERID>"
        "<DATE>20250401</DATE>"
        "<EFFECTIVEDATE>20250401</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>SI/BCPND</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Party C</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
        "<AMOUNT>6000.00</AMOUNT>"
        "<BILLALLOCATIONS.LIST>"
        "<BILLTYPE>New Ref</BILLTYPE>"
        "<NAME>SI/BCPND</NAME>"
        "<AMOUNT>6000.00</AMOUNT>"
        "<BILLCREDITPERIOD>"
        "<DUEONDATE>20250501</DUEONDATE>"
        "</BILLCREDITPERIOD>"
        "</BILLALLOCATIONS.LIST>"
        "</LEDGERENTRIES.LIST>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Sales</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
        "<AMOUNT>-6000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1
    assert vouchers[0].bill_allocations[0].bill_credit_period is None


def test_parse_voucher_complex_amount_is_debit_false() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="complex-debit-guid" VCHTYPE="Sales">'
        "<ALTERID>210</ALTERID>"
        "<DATE>20250401</DATE>"
        "<EFFECTIVEDATE>20250401</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>SI/CDB</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Credit Account</LEDGERNAME>"
        "<AMOUNT><AMOUNT>0</AMOUNT><ISDEBIT>False</ISDEBIT></AMOUNT>"
        "<COSTCENTRE.LIST>"
        "<COSTCENTRENAME>Branch A</COSTCENTRENAME>"
        "<AMOUNT><AMOUNT>0</AMOUNT><ISDEBIT>False</ISDEBIT></AMOUNT>"
        "</COSTCENTRE.LIST>"
        "</LEDGERENTRIES.LIST>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Sales</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>"
        "<AMOUNT>-3000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1


def test_parse_voucher_inventory_complex_amount() -> None:
    xml = (
        "<ENVELOPE><BODY><DATA><TALLYMESSAGE>"
        '<VOUCHER GUID="inv-complex-guid" VCHTYPE="Sales">'
        "<ALTERID>211</ALTERID>"
        "<DATE>20250401</DATE>"
        "<EFFECTIVEDATE>20250401</EFFECTIVEDATE>"
        "<VOUCHERNUMBER>SI/IC</VOUCHERNUMBER>"
        "<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>"
        "<ISCANCELLED>No</ISCANCELLED>"
        "<ISOPTIONAL>No</ISOPTIONAL>"
        "<ISPOSTDATED>No</ISPOSTDATED>"
        "<ISVOID>No</ISVOID>"
        "<LEDGERENTRIES.LIST>"
        "<LEDGERNAME>Party D</LEDGERNAME>"
        "<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>"
        "<AMOUNT>12000.00</AMOUNT>"
        "</LEDGERENTRIES.LIST>"
        "<INVENTORYENTRIES.LIST>"
        "<STOCKITEMNAME>Widget Y</STOCKITEMNAME>"
        "<ACTUALQTY>5 Nos</ACTUALQTY>"
        "<RATE>2400.00/Nos</RATE>"
        "<AMOUNT><AMOUNT>0</AMOUNT><ISDEBIT>True</ISDEBIT></AMOUNT>"
        "<GODOWN>Main</GODOWN>"
        "<BATCH>B001</BATCH>"
        "</INVENTORYENTRIES.LIST>"
        "</VOUCHER>"
        "</TALLYMESSAGE></DATA></BODY></ENVELOPE>"
    )
    vouchers = parser.parse_vouchers(xml)
    assert len(vouchers) == 1
    assert vouchers[0].inventory_entries[0].godown == "Main"
    assert vouchers[0].inventory_entries[0].batch == "B001"


# --- Report parsing tests (10d) ---


class TestParseBalanceSheet:
    BALANCE_SHEET_XML = """<ENVELOPE>
<BSNAME><DSPDISPNAME>Capital Account</DSPDISPNAME></BSNAME>
<BSCLOSAMT><DSPCLDRAMT><DSPCLDRAMTA></DSPCLDRAMTA></DSPCLDRAMT>
<DSPCLCRAMT><DSPCLCRAMTA>100000.00</DSPCLCRAMTA></DSPCLCRAMT></BSCLOSAMT>
<BSNAME><DSPDISPNAME>Current Assets</DSPDISPNAME></BSNAME>
<BSCLOSAMT><DSPCLDRAMT><DSPCLDRAMTA>50000.00</DSPCLDRAMTA></DSPCLDRAMT>
<DSPCLCRAMT><DSPCLCRAMTA></DSPCLCRAMTA></DSPCLCRAMT></BSCLOSAMT>
<BSNAME><DSPDISPNAME>Current Liabilities</DSPDISPNAME></BSNAME>
<BSCLOSAMT><DSPCLDRAMT><DSPCLDRAMTA></DSPCLDRAMTA></DSPCLDRAMT>
<DSPCLCRAMT><DSPCLCRAMTA>25000.00</DSPCLCRAMTA></DSPCLCRAMT></BSCLOSAMT>
</ENVELOPE>"""

    def test_parse_balance_sheet_report(self) -> None:
        report = TallyXMLParser.parse_report(
            self.BALANCE_SHEET_XML,
            report_name="Balance Sheet",
        )
        assert report.report_type == "Balance Sheet"
        assert len(report.lines) == 3
        assert report.lines[0].name == "Capital Account"
        assert report.lines[0].closing_credit == Decimal("100000")
        assert report.lines[1].name == "Current Assets"
        assert report.lines[1].closing_debit == Decimal("50000")
        assert report.lines[2].name == "Current Liabilities"
        assert report.lines[2].closing_credit == Decimal("25000")

    def test_parse_balance_sheet_empty(self) -> None:
        report = TallyXMLParser.parse_report(
            "<ENVELOPE></ENVELOPE>",
            report_name="Balance Sheet",
        )
        assert report.report_type == "Balance Sheet"
        assert len(report.lines) == 0

    def test_parse_balance_sheet_with_dates(self) -> None:
        report = TallyXMLParser.parse_report(
            self.BALANCE_SHEET_XML,
            report_name="Balance Sheet",
            from_date=date(2025, 4, 1),
            to_date=date(2025, 12, 31),
        )
        assert report.from_date == date(2025, 4, 1)
        assert report.to_date == date(2025, 12, 31)


class TestParseProfitLoss:
    PL_XML = """<ENVELOPE>
<PLNAME><DSPDISPNAME>Direct Income</DSPDISPNAME></PLNAME>
<PLCLOSAMT><DSPCLDRAMT><DSPCLDRAMTA></DSPCLDRAMTA></DSPCLDRAMT>
<DSPCLCRAMT><DSPCLCRAMTA>75000.00</DSPCLCRAMTA></DSPCLCRAMT></PLCLOSAMT>
<PLNAME><DSPDISPNAME>Indirect Expenses</DSPDISPNAME></PLNAME>
<PLCLOSAMT><DSPCLDRAMT><DSPCLDRAMTA>30000.00</DSPCLDRAMTA></DSPCLDRAMT>
<DSPCLCRAMT><DSPCLCRAMTA></DSPCLCRAMTA></DSPCLCRAMT></PLCLOSAMT>
</ENVELOPE>"""

    def test_parse_profit_loss_report(self) -> None:
        report = TallyXMLParser.parse_report(
            self.PL_XML,
            report_name="Profit & Loss",
        )
        assert report.report_type == "Profit & Loss"
        assert len(report.lines) == 2
        assert report.lines[0].name == "Direct Income"
        assert report.lines[0].closing_credit == Decimal("75000")
        assert report.lines[1].name == "Indirect Expenses"
        assert report.lines[1].closing_debit == Decimal("30000")


class TestParseTrialBalanceReport:
    TB_XML = """<ENVELOPE>
<DSPACCNAME><DSPDISPNAME>Cash</DSPDISPNAME></DSPACCNAME>
<DSPACCINFO><DSPCLDRAMT><DSPCLDRAMTA>12000.00</DSPCLDRAMTA></DSPCLDRAMT>
<DSPCLCRAMT><DSPCLCRAMTA></DSPCLCRAMTA></DSPCLCRAMT></DSPACCINFO>
<DSPACCNAME><DSPDISPNAME>Bank of India</DSPDISPNAME></DSPACCNAME>
<DSPACCINFO><DSPCLDRAMT><DSPCLDRAMTA></DSPCLDRAMTA></DSPCLDRAMT>
<DSPCLCRAMT><DSPCLCRAMTA>351265.00</DSPCLCRAMTA></DSPCLCRAMT></DSPACCINFO>
</ENVELOPE>"""

    def test_parse_trial_balance_report(self) -> None:
        report = TallyXMLParser.parse_report(
            self.TB_XML,
            report_name="Trial Balance",
        )
        assert report.report_type == "Trial Balance"
        assert len(report.trial_balance) == 2
        assert report.trial_balance[0].ledger == "Cash"
        assert report.trial_balance[0].closing_debit == Decimal("12000")
        assert report.trial_balance[1].ledger == "Bank of India"
        assert report.trial_balance[1].closing_credit == Decimal("351265")

    def test_trial_balance_empty(self) -> None:
        report = TallyXMLParser.parse_report(
            "<ENVELOPE></ENVELOPE>",
            report_name="Trial Balance",
        )
        assert report.report_type == "Trial Balance"
        assert len(report.trial_balance) == 0


class TestParseDayBookReport:
    DAY_BOOK_XML = """<ENVELOPE>
<BODY><DATA><TALLYMESSAGE>
<VOUCHER>
<DATE>20250415</DATE>
<VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
<VOUCHERNUMBER>5</VOUCHERNUMBER>
<NARRATION>Sold goods</NARRATION>
<GUID>ABC123</GUID>
</VOUCHER>
<VOUCHER>
<DATE>20250416</DATE>
<VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
<VOUCHERNUMBER>2</VOUCHERNUMBER>
</VOUCHER>
</TALLYMESSAGE></DATA></BODY>
</ENVELOPE>"""

    def test_parse_day_book_report(self) -> None:
        report = TallyXMLParser.parse_report(
            self.DAY_BOOK_XML,
            report_name="Day Book",
        )
        assert report.report_type == "Day Book"
        assert len(report.vouchers) == 2
        assert report.vouchers[0]["voucher_type"] == "Sales"
        assert report.vouchers[0]["voucher_number"] == "5"
        assert report.vouchers[0]["narration"] == "Sold goods"
        assert report.vouchers[0]["guid"] == "ABC123"
        assert report.vouchers[0]["date"] == date(2025, 4, 15)
        assert report.vouchers[1]["voucher_type"] == "Purchase"

    def test_day_book_empty(self) -> None:
        report = TallyXMLParser.parse_report(
            "<ENVELOPE></ENVELOPE>",
            report_name="Day Book",
        )
        assert report.report_type == "Day Book"
        assert len(report.vouchers) == 0


class TestParseReportUnknown:
    def test_unknown_report_type(self) -> None:
        report = TallyXMLParser.parse_report(
            "<ENVELOPE></ENVELOPE>",
            report_name="Custom Report",
        )
        assert report.report_type == "Unknown"

    def test_invalid_xml(self) -> None:
        report = TallyXMLParser.parse_report(
            "<invalid",
            report_name="Balance Sheet",
        )
        assert report.report_type == "Balance Sheet"
        assert len(report.lines) == 0

    def test_report_type_detection_case_insensitive(self) -> None:
        report = TallyXMLParser.parse_report(
            "<ENVELOPE></ENVELOPE>",
            report_name="balance sheet",
        )
        assert report.report_type == "Balance Sheet"

        report2 = TallyXMLParser.parse_report(
            "<ENVELOPE></ENVELOPE>",
            report_name="PROFIT & LOSS",
        )
        assert report2.report_type == "Profit & Loss"


json_parser = TallyJSONParser()


class TestJSONParserLedgers:
    def test_parse_ledgers_json(self) -> None:
        ledgers = json_parser.parse_ledgers_json(SAMPLE_LEDGERS_JSON)
        assert len(ledgers) >= 3
        assert ledgers[0].name == "Cash"
        assert ledgers[0].guid == "guid-cash-001"
        assert ledgers[0].alter_id == 100
        assert ledgers[0].parent_group == "Cash-in-Hand"
        assert ledgers[0].closing_balance == Decimal("45000")

    def test_parse_ledgers_json_revenue(self) -> None:
        ledgers = json_parser.parse_ledgers_json(SAMPLE_LEDGERS_JSON)
        sales = [ld for ld in ledgers if ld.name == "Sales"][0]
        assert sales.is_revenue is True
        assert sales.closing_balance == Decimal("-850000")

    def test_parse_ledgers_json_empty(self) -> None:
        ledgers = json_parser.parse_ledgers_json(
            {"status": "1", "data": {"tallymessage": []}}
        )
        assert ledgers == []

    def test_parse_ledgers_json_invalid_message(self) -> None:
        data = {
            "status": "1",
            "data": {
                "tallymessage": [
                    {"notaledger": {"name": "X"}},
                    {"ledger": {"name": "Valid"}},
                ]
            },
        }
        ledgers = json_parser.parse_ledgers_json(data)
        assert len(ledgers) == 1


class TestJSONParserGroups:
    def test_parse_groups_json(self) -> None:
        groups = json_parser.parse_groups_json(SAMPLE_GROUPS_JSON)
        assert len(groups) >= 2
        assert groups[0].name == "Sundry Debtors"
        assert groups[0].guid == "guid-grp-001"
        assert groups[0].alter_id == 10
        assert groups[0].primary_group == "Assets"

    def test_parse_groups_net_debit_credit(self) -> None:
        groups = json_parser.parse_groups_json(SAMPLE_GROUPS_JSON)
        creditors = [g for g in groups if g.name == "Sundry Creditors"][0]
        assert creditors.net_debit_credit == "Cr"


class TestJSONParserStockItems:
    def test_parse_stock_items_json(self) -> None:
        items = json_parser.parse_stock_items_json(SAMPLE_STOCK_ITEMS_JSON)
        assert len(items) >= 1
        assert items[0].name == "Widget A"
        assert items[0].gst_rate == Decimal("18")
        assert items[0].hsn_code == "8471"
        assert items[0].closing_quantity == Decimal("150")
        assert items[0].closing_value == Decimal("45000")


class TestJSONParserUnits:
    def test_parse_units_json(self) -> None:
        units = json_parser.parse_units_json(SAMPLE_UNITS_JSON)
        assert len(units) >= 1
        assert units[0].name == "Nos"
        assert units[0].unit_type == "Simple"
        assert units[0].decimal_places == 0


class TestJSONParserStockGroups:
    def test_parse_stock_groups_json(self) -> None:
        groups = json_parser.parse_stock_groups_json(SAMPLE_STOCK_GROUPS_JSON)
        assert len(groups) >= 1
        assert groups[0].name == "Stock-in-Trade"
        assert groups[0].should_quantities_add is True


class TestJSONParserCostCenters:
    def test_parse_cost_centers_json(self) -> None:
        centers = json_parser.parse_cost_centers_json(SAMPLE_COST_CENTERS_JSON)
        assert len(centers) >= 1
        assert centers[0].name == "Head Office"
        assert centers[0].cost_centre_type == "Primary"


class TestJSONParserVoucherTypes:
    def test_parse_voucher_types_json(self) -> None:
        vtypes = json_parser.parse_voucher_types_json(SAMPLE_VOUCHER_TYPES_JSON)
        assert len(vtypes) >= 1
        assert vtypes[0].name == "Sales"
        assert vtypes[0].parent == "Accounting Vouchers"


class TestJSONParserVouchers:
    def test_parse_vouchers_json(self) -> None:
        vouchers = json_parser.parse_vouchers_json(SAMPLE_VOUCHERS_JSON)
        assert len(vouchers) >= 2
        v1 = vouchers[0]
        assert v1.guid == "guid-v-001"
        assert v1.voucher_type == "Sales"
        assert v1.date == date(2025, 4, 1)
        assert v1.voucher_number == "SI/001/25"

    def test_parse_vouchers_json_ledger_entries(self) -> None:
        vouchers = json_parser.parse_vouchers_json(SAMPLE_VOUCHERS_JSON)
        v1 = vouchers[0]
        assert len(v1.ledger_entries) == 4
        assert v1.ledger_entries[0].ledger_name == "Sharma Trading Co"
        assert v1.ledger_entries[0].amount == Decimal("50000")
        assert v1.ledger_entries[1].ledger_name == "Sales"
        assert v1.ledger_entries[1].amount == Decimal("-50000")

    def test_parse_vouchers_json_gst_amount(self) -> None:
        vouchers = json_parser.parse_vouchers_json(SAMPLE_VOUCHERS_JSON)
        v1 = vouchers[0]
        assert v1.gst_amount > Decimal("0")

    def test_parse_vouchers_json_cancelled(self) -> None:
        vouchers = json_parser.parse_vouchers_json(SAMPLE_VOUCHERS_JSON)
        for v in vouchers:
            if v.guid == "guid-v-001":
                assert v.is_cancelled is False

    def test_parse_vouchers_json_empty(self) -> None:
        vouchers = json_parser.parse_vouchers_json(
            {"status": "1", "data": {"tallymessage": []}}
        )
        assert vouchers == []

    def test_parse_vouchers_json_uses_ledgerentries_fallback(self) -> None:
        data = {
            "status": "1",
            "data": {
                "tallymessage": [
                    {
                        "voucher": {
                            "guid": "guid-v-fb",
                            "alterid": "600",
                            "date": "20250601",
                            "vouchernumber": "FB/001",
                            "vouchertypename": "Payment",
                            "ledgerentries.list": [
                                {
                                    "ledgername": "Cash",
                                    "amount": "-500.00",
                                },
                                {
                                    "ledgername": "Expense",
                                    "amount": "500.00",
                                },
                            ],
                        }
                    }
                ]
            },
        }
        vouchers = json_parser.parse_vouchers_json(data)
        assert len(vouchers) == 1
        assert len(vouchers[0].ledger_entries) == 2


class TestJSONParserReport:
    def test_parse_report_json_balance_sheet(self) -> None:
        data = {
            "status": "1",
            "data": {
                "dspaccname": [
                    {"dspdispname": "Capital"},
                    {"dspdispname": "Cash"},
                ],
                "dspaccinfo": [
                    {
                        "dspcldramt": {"dspcldramta": "0"},
                        "dspclcramt": {"dspclcramta": "100000"},
                    },
                    {
                        "dspcldramt": {"dspcldramta": "100000"},
                        "dspclcramt": {"dspclcramta": "0"},
                    },
                ],
            },
        }
        report = TallyJSONParser.parse_report_json(
            data, report_name="Balance Sheet", from_date=date(2025, 1, 1)
        )
        assert report.report_type == "Balance Sheet"
        assert len(report.lines) == 2

    def test_parse_report_json_trial_balance(self) -> None:
        data = {
            "status": "1",
            "data": {
                "dspaccname": [{"dspdispname": "Cash"}],
                "dspaccinfo": [
                    {
                        "dspcldramt": {"dspcldramta": "50000"},
                        "dspclcramt": {"dspclcramta": "0"},
                    },
                ],
            },
        }
        report = TallyJSONParser.parse_report_json(
            data, report_name="Trial Balance"
        )
        assert report.report_type == "Trial Balance"
        assert len(report.trial_balance) == 1
        assert report.trial_balance[0].closing_debit == Decimal("50000")

    def test_parse_report_json_day_book(self) -> None:
        data = {
            "status": "1",
            "data": {
                "tallymessage": [
                    {
                        "voucher": {
                            "guid": "g1",
                            "date": "20250401",
                            "vouchertypename": "Sales",
                            "vouchernumber": "1",
                        }
                    }
                ]
            },
        }
        report = TallyJSONParser.parse_report_json(
            data, report_name="Day Book"
        )
        assert report.report_type == "Day Book"
        assert len(report.vouchers) == 1

    def test_parse_report_json_unknown(self) -> None:
        report = TallyJSONParser.parse_report_json(
            {"status": "1", "data": {}}, report_name="Custom"
        )
        assert report.report_type == "Unknown"

    def test_parse_report_json_empty_data(self) -> None:
        report = TallyJSONParser.parse_report_json(
            {"status": "1", "data": {"dspaccname": [], "dspaccinfo": []}},
            report_name="Balance Sheet",
        )
        assert len(report.lines) == 0


class TestJSONParserHelperMethods:
    def test_get_val_none_obj(self) -> None:
        assert TallyJSONParser._get_val(None, "key") == ""
        assert TallyJSONParser._get_val(None, "key", "default") == "default"

    def test_get_val_missing_key(self) -> None:
        assert TallyJSONParser._get_val({}, "key") == ""
        assert TallyJSONParser._get_val({"other": 1}, "key") == ""

    def test_get_val_int_value(self) -> None:
        assert TallyJSONParser._get_val({"key": 42}, "key") == "42"

    def test_get_list_none(self) -> None:
        assert TallyJSONParser._get_list({}, "key") == []

    def test_get_list_single_dict(self) -> None:
        result = TallyJSONParser._get_list({"key": {"a": 1}}, "key")
        assert len(result) == 1
        assert result[0] == {"a": 1}

    def test_get_list_array(self) -> None:
        result = TallyJSONParser._get_list(
            {"key": [{"a": 1}, {"b": 2}]}, "key"
        )
        assert len(result) == 2

    def test_get_tally_messages_dict(self) -> None:
        data = {"data": {"tallymessage": {"ledger": {"name": "X"}}}}
        msgs = TallyJSONParser._get_tally_messages(data)
        assert len(msgs) == 1

    def test_get_tally_messages_list(self) -> None:
        data = {
            "data": {
                "tallymessage": [
                    {"ledger": {"name": "X"}},
                    {"ledger": {"name": "Y"}},
                ]
            }
        }
        msgs = TallyJSONParser._get_tally_messages(data)
        assert len(msgs) == 2

    def test_parse_bill_credit_period_json_none(self) -> None:
        assert TallyJSONParser._parse_bill_credit_period_json(None) is None

    def test_parse_bill_credit_period_json_int(self) -> None:
        assert TallyJSONParser._parse_bill_credit_period_json(30) == 30

    def test_parse_bill_credit_period_json_string(self) -> None:
        assert TallyJSONParser._parse_bill_credit_period_json("45") == 45

    def test_parse_bill_credit_period_json_dict(self) -> None:
        assert (
            TallyJSONParser._parse_bill_credit_period_json({"indays": "60"}) == 60
        )

    def test_parse_bill_credit_period_json_invalid_string(self) -> None:
        assert (
            TallyJSONParser._parse_bill_credit_period_json("abc") is None
        )


class TestCurrencyEntityCodes:
    def test_fix_currency_entities_aed(self) -> None:
        xml = "<NAME>Price &#8387; 100</NAME>"
        fixed = TallyXMLParser._fix_currency_entities(xml)
        assert "\u20c3" in fixed
        assert "&#8387;" not in fixed

    def test_fix_currency_entities_sar(self) -> None:
        xml = "<NAME>Amount &#8385; 500</NAME>"
        fixed = TallyXMLParser._fix_currency_entities(xml)
        assert "\u20c1" in fixed
        assert "&#8385;" not in fixed

    def test_fix_currency_entities_no_change(self) -> None:
        xml = "<NAME>Cash</NAME>"
        fixed = TallyXMLParser._fix_currency_entities(xml)
        assert fixed == xml

    def test_fix_currency_entities_both(self) -> None:
        xml = "<A>&#8387;</A><B>&#8385;</B>"
        fixed = TallyXMLParser._fix_currency_entities(xml)
        assert "\u20c3" in fixed
        assert "\u20c1" in fixed
