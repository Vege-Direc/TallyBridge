"""Mock Tally HTTP server — see SPECS.md §11a."""

import json
from decimal import Decimal
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from werkzeug import Response

SAMPLE_LEDGERS = [
    ("guid-cash-001", 100, "Cash", "Cash-in-Hand", "45000.00 Dr", False, None),
    ("guid-hdfc-001", 101, "HDFC Bank", "Bank Accounts", "250000.00 Dr", False, None),
    ("guid-icici-001", 102, "ICICI Bank", "Bank Accounts", "75000.00 Dr", False, None),
    ("guid-sales-001", 103, "Sales", "Sales Accounts", "850000.00 Cr", True, None),
    (
        "guid-purch-001",
        104,
        "Purchase",
        "Purchase Accounts",
        "420000.00 Dr",
        True,
        None,
    ),
    (
        "guid-party-001",
        105,
        "Sharma Trading Co",
        "Sundry Debtors",
        "75000.00 Dr",
        False,
        "27AABCS1429B1Z1",
    ),
    (
        "guid-party-002",
        106,
        "Mehta Suppliers",
        "Sundry Creditors",
        "42000.00 Cr",
        False,
        "27AAACM2850K1Z1",
    ),
    (
        "guid-party-003",
        107,
        "Patel Enterprises",
        "Sundry Debtors",
        "35000.00 Dr",
        False,
        None,
    ),
    ("guid-cgst-001", 108, "CGST", "Duties & Taxes", "12500.00 Cr", False, None),
    (
        "guid-hindi-001",
        109,
        "शर्मा एंड कंपनी",
        "Sundry Debtors",
        "15000.00 Dr",
        False,
        None,
    ),
]

SAMPLE_GROUPS = [
    ("guid-grp-001", 10, "Sundry Debtors", "Current Assets", "Assets", False, "Dr"),
    (
        "guid-grp-002",
        11,
        "Sundry Creditors",
        "Current Liabilities",
        "Liabilities",
        False,
        "Cr",
    ),
    ("guid-grp-003", 12, "Sales Accounts", "Revenue", "Income", True, "Cr"),
]

SAMPLE_UNITS = [
    ("guid-unit-001", 300, "Nos", "Simple", "Nos", 0),
    ("guid-unit-002", 301, "Kgs", "Simple", "Kg", 3),
    ("guid-unit-003", 302, "Ltrs", "Simple", "L", 3),
    ("guid-unit-004", 303, "Boxes", "Simple", "Box", 0),
]

SAMPLE_STOCK_GROUPS = [
    ("guid-sg-001", 310, "Stock-in-Trade", "Primary", True),
    ("guid-sg-002", 311, "Finished Goods", "Primary", True),
]

SAMPLE_STOCK_ITEMS = [
    (
        "guid-item-001",
        200,
        "Widget A",
        "Stock-in-Trade",
        "Nos",
        18.0,
        "8471",
        150,
        "45000.00",
    ),
    (
        "guid-item-002",
        201,
        "Widget B",
        "Stock-in-Trade",
        "Kgs",
        12.0,
        "3926",
        80,
        "24000.00",
    ),
    ("guid-item-003", 202, "Widget C", "Stock-in-Trade", "Nos", 5.0, "8473", 0, "0.00"),
]

SAMPLE_COST_CENTERS = [
    ("guid-cc-001", 400, "Head Office", "Primary", "Primary"),
    ("guid-cc-002", 401, "Mumbai Branch", "Primary", "Sub"),
    ("guid-cc-003", 402, "Delhi Branch", "Primary", "Sub"),
]

SAMPLE_GODOWNS = [
    ("guid-gd-001", 410, "Main Store", None),
    ("guid-gd-002", 411, "Mumbai Warehouse", "Main Store"),
    ("guid-gd-003", 412, "Delhi Warehouse", "Main Store"),
]

SAMPLE_VOUCHERS = [
    (
        "guid-v-001",
        500,
        "Sales",
        "20250401",
        "20250401",
        "Sharma Trading Co",
        "SI/001/25",
        "50000.00",
        False,
        False,
        False,
        "Admin",
    ),
    (
        "guid-v-002",
        501,
        "Sales",
        "20250405",
        "20250405",
        "Patel Enterprises",
        "SI/002/25",
        "35000.00",
        False,
        False,
        False,
        "Admin",
    ),
    (
        "guid-v-003",
        502,
        "Sales",
        "20250410",
        "20250410",
        "Sharma Trading Co",
        "SI/003/25",
        "25000.00",
        False,
        False,
        False,
        "Admin",
    ),
    (
        "guid-v-004",
        503,
        "Purchase",
        "20250403",
        "20250401",
        "Mehta Suppliers",
        "PI/001/25",
        "42000.00",
        False,
        False,
        False,
        "Manager",
    ),
    (
        "guid-v-005",
        504,
        "Payment",
        "20250408",
        "20250408",
        "Mehta Suppliers",
        "PMT/001/25",
        "20000.00",
        False,
        False,
        False,
        "Admin",
    ),
    (
        "guid-v-006",
        505,
        "Sales",
        "20250412",
        "20250412",
        "Patel Enterprises",
        "SI/004/25",
        "15000.00",
        True,
        False,
        False,
        "Admin",
    ),
    (
        "guid-v-007",
        506,
        "Payment",
        "20250501",
        "20250501",
        "Sharma Trading Co",
        "PMT/002/25",
        "10000.00",
        False,
        False,
        True,
        "Admin",
    ),
]

SAMPLE_VOUCHERS_ALL_LEDGER = [
    (
        "guid-v-008",
        507,
        "Sales",
        "20250415",
        "20250415",
        "Sharma Trading Co",
        "SI/005/25",
        "30000.00",
        False,
        False,
        False,
        "Admin",
    ),
]


def build_ledger_xml(ledgers: list | None = None) -> str:
    """Return Tally-format XML string for ledger collection."""
    ledgers = ledgers or SAMPLE_LEDGERS
    lines = ["<ENVELOPE><BODY><DATA><TALLYMESSAGE>"]
    for guid, alter_id, name, parent, closing, is_revenue, gstin in ledgers:
        lines.append(f'<LEDGER NAME="{xml_escape(name)}" GUID="{guid}">')
        lines.append(f"<ALTERID>{alter_id}</ALTERID>")
        lines.append(f"<NAME>{xml_escape(name)}</NAME>")
        lines.append(f"<PARENT>{xml_escape(parent)}</PARENT>")
        lines.append(f"<CLOSINGBALANCE>{closing}</CLOSINGBALANCE>")
        lines.append("<OPENINGBALANCE>0.00 Dr</OPENINGBALANCE>")
        lines.append(f"<ISREVENUE>{'Yes' if is_revenue else 'No'}</ISREVENUE>")
        lines.append("<AFFECTSGROSSPROFIT>No</AFFECTSGROSSPROFIT>")
        if gstin:
            lines.append(f"<GSTIN>{gstin}</GSTIN>")
        lines.append(f"<LEDMAILINGNAME>{xml_escape(name)}</LEDMAILINGNAME>")
        lines.append("</LEDGER>")
    lines.append("</TALLYMESSAGE></DATA></BODY></ENVELOPE>")
    return "".join(lines)


def build_group_xml(groups: list | None = None) -> str:
    """Return Tally-format XML string for group collection."""
    groups = groups or SAMPLE_GROUPS
    lines = ["<ENVELOPE><BODY><DATA><TALLYMESSAGE>"]
    for guid, alter_id, name, parent, primary, is_revenue, net_dc in groups:
        lines.append(f'<GROUP NAME="{name}" GUID="{guid}">')
        lines.append(f"<ALTERID>{alter_id}</ALTERID>")
        lines.append(f"<NAME>{name}</NAME>")
        lines.append(f"<PARENT>{parent}</PARENT>")
        lines.append(f"<PRIMARYGROUP>{primary}</PRIMARYGROUP>")
        lines.append(f"<ISREVENUE>{'Yes' if is_revenue else 'No'}</ISREVENUE>")
        lines.append("<AFFECTSGROSSPROFIT>No</AFFECTSGROSSPROFIT>")
        lines.append(f"<NETDEBITCREDIT>{net_dc}</NETDEBITCREDIT>")
        lines.append("</GROUP>")
    lines.append("</TALLYMESSAGE></DATA></BODY></ENVELOPE>")
    return "".join(lines)


def build_unit_xml(units: list | None = None) -> str:
    """Return Tally-format XML for unit of measure collection."""
    units = units or SAMPLE_UNITS
    lines = ["<ENVELOPE><BODY><DATA><TALLYMESSAGE>"]
    for guid, alter_id, name, unit_type, symbol, decimal_places in units:
        lines.append(f'<UNIT NAME="{name}" GUID="{guid}">')
        lines.append(f"<ALTERID>{alter_id}</ALTERID>")
        lines.append(f"<NAME>{name}</NAME>")
        lines.append(f"<UNITTYPE>{unit_type}</UNITTYPE>")
        if symbol:
            lines.append(f"<SYMBOL>{symbol}</SYMBOL>")
        lines.append(f"<DECIMALPLACES>{decimal_places}</DECIMALPLACES>")
        lines.append("</UNIT>")
    lines.append("</TALLYMESSAGE></DATA></BODY></ENVELOPE>")
    return "".join(lines)


def build_stock_group_xml(stock_groups: list | None = None) -> str:
    """Return Tally-format XML for stock group collection."""
    stock_groups = stock_groups or SAMPLE_STOCK_GROUPS
    lines = ["<ENVELOPE><BODY><DATA><TALLYMESSAGE>"]
    for guid, alter_id, name, parent, should_add in stock_groups:
        lines.append(f'<STOCKGROUP NAME="{name}" GUID="{guid}">')
        lines.append(f"<ALTERID>{alter_id}</ALTERID>")
        lines.append(f"<NAME>{name}</NAME>")
        lines.append(f"<PARENT>{parent}</PARENT>")
        lines.append(
            f"<SHOULDQUANTITIESADD>"
            f"{'Yes' if should_add else 'No'}</SHOULDQUANTITIESADD>"
        )
        lines.append("</STOCKGROUP>")
    lines.append("</TALLYMESSAGE></DATA></BODY></ENVELOPE>")
    return "".join(lines)


def build_stock_item_xml(items: list | None = None) -> str:
    """Return Tally-format XML for stock item collection."""
    items = items or SAMPLE_STOCK_ITEMS
    lines = ["<ENVELOPE><BODY><DATA><TALLYMESSAGE>"]
    for (
        guid,
        alter_id,
        name,
        parent,
        unit,
        gst_rate,
        hsn,
        closing_qty,
        closing_val,
    ) in items:
        lines.append(f'<STOCKITEM NAME="{name}" GUID="{guid}">')
        lines.append(f"<ALTERID>{alter_id}</ALTERID>")
        lines.append(f"<NAME>{name}</NAME>")
        lines.append(f"<PARENT>{parent}</PARENT>")
        lines.append(f"<BASEUNITS>{unit}</BASEUNITS>")
        lines.append(f"<GSTRATE>{gst_rate}</GSTRATE>")
        lines.append(f"<HSNCODE>{hsn}</HSNCODE>")
        lines.append(f"<CLOSINGBALANCE>{closing_qty} {unit}</CLOSINGBALANCE>")
        lines.append(f"<CLOSINGVALUE>{closing_val}</CLOSINGVALUE>")
        lines.append("<OPENINGBALANCE>0.00 Nos</OPENINGBALANCE>")
        lines.append("</STOCKITEM>")
    lines.append("</TALLYMESSAGE></DATA></BODY></ENVELOPE>")
    return "".join(lines)


def build_cost_center_xml(cost_centers: list | None = None) -> str:
    """Return Tally-format XML for cost centre collection."""
    cost_centers = cost_centers or SAMPLE_COST_CENTERS
    lines = ["<ENVELOPE><BODY><DATA><TALLYMESSAGE>"]
    for guid, alter_id, name, parent, cc_type in cost_centers:
        lines.append(f'<COSTCENTRE NAME="{name}" GUID="{guid}">')
        lines.append(f"<ALTERID>{alter_id}</ALTERID>")
        lines.append(f"<NAME>{name}</NAME>")
        lines.append(f"<PARENT>{parent}</PARENT>")
        lines.append(f"<COSTCENTRETYPE>{cc_type}</COSTCENTRETYPE>")
        lines.append("</COSTCENTRE>")
    lines.append("</TALLYMESSAGE></DATA></BODY></ENVELOPE>")
    return "".join(lines)


def build_godown_xml(godowns: list | None = None) -> str:
    """Return Tally-format XML for godown collection."""
    godowns = godowns or SAMPLE_GODOWNS
    lines = ["<ENVELOPE><BODY><DATA><TALLYMESSAGE>"]
    for guid, alter_id, name, parent in godowns:
        lines.append(f'<GODOWN NAME="{name}" GUID="{guid}">')
        lines.append(f"<ALTERID>{alter_id}</ALTERID>")
        lines.append(f"<NAME>{name}</NAME>")
        if parent:
            lines.append(f"<PARENT>{parent}</PARENT>")
        lines.append("</GODOWN>")
    lines.append("</TALLYMESSAGE></DATA></BODY></ENVELOPE>")
    return "".join(lines)


def build_voucher_type_xml() -> str:
    """Return minimal voucher type XML."""
    lines = ["<ENVELOPE><BODY><DATA><TALLYMESSAGE>"]
    vtypes = [
        ("guid-vt-001", 400, "Sales", "Accounting Vouchers"),
        ("guid-vt-002", 401, "Purchase", "Accounting Vouchers"),
        ("guid-vt-003", 402, "Payment", "Accounting Vouchers"),
        ("guid-vt-004", 403, "Receipt", "Accounting Vouchers"),
    ]
    for guid, alter_id, name, parent in vtypes:
        lines.append(f'<VOUCHERTYPE NAME="{name}" GUID="{guid}">')
        lines.append(f"<ALTERID>{alter_id}</ALTERID>")
        lines.append(f"<NAME>{name}</NAME>")
        lines.append(f"<PARENT>{parent}</PARENT>")
        lines.append("</VOUCHERTYPE>")
    lines.append("</TALLYMESSAGE></DATA></BODY></ENVELOPE>")
    return "".join(lines)


def build_voucher_xml(vouchers: list | None = None) -> str:
    """Return Tally-format XML with nested LEDGERENTRIES.LIST."""
    vouchers = vouchers or SAMPLE_VOUCHERS
    lines = ["<ENVELOPE><BODY><DATA><TALLYMESSAGE>"]
    for (
        guid,
        alter_id,
        vtype,
        vdate,
        eff_date,
        party,
        vnum,
        amount,
        is_cancelled,
        is_void,
        is_postdated,
        entered_by,
    ) in vouchers:
        is_deemed_positive = "Yes" if vtype in ("Sales", "Payment") else "No"
        lines.append(f'<VOUCHER VCHTYPE="{vtype}" GUID="{guid}">')
        lines.append(f"<ALTERID>{alter_id}</ALTERID>")
        lines.append(f"<DATE>{vdate}</DATE>")
        lines.append(f"<EFFECTIVEDATE>{eff_date}</EFFECTIVEDATE>")
        lines.append(f"<VOUCHERNUMBER>{vnum}</VOUCHERNUMBER>")
        lines.append(f"<VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>")
        lines.append(f"<PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>")
        lines.append(f"<ISCANCELLED>{'Yes' if is_cancelled else 'No'}</ISCANCELLED>")
        lines.append("<ISOPTIONAL>No</ISOPTIONAL>")
        lines.append(f"<ISPOSTDATED>{'Yes' if is_postdated else 'No'}</ISPOSTDATED>")
        lines.append(f"<ISVOID>{'Yes' if is_void else 'No'}</ISVOID>")
        lines.append(f"<ENTEREDBY>{entered_by}</ENTEREDBY>")
        if guid == "guid-v-001":
            lines.append("<IRN>3A3B3C3D3E3F3G3H3I3J3K3L3M3N</IRN>")
            lines.append("<ACKNO>123456789</ACKNO>")
            lines.append("<ACKDT>20250401</ACKDT>")
            lines.append("<QRCODE>https://einvoice1.gst.gov.in/qr/3A3B</QRCODE>")
            lines.append("<ISEINVOICE>Yes</ISEINVOICE>")
            lines.append("<EWAYBILLNUMBER>271003456789</EWAYBILLNUMBER>")
            lines.append("<EWAYBILLDATE>20250401</EWAYBILLDATE>")
            lines.append("<EWAYVALIDTILL>20250415</EWAYVALIDTILL>")
            lines.append("<TRANSPORTERNAME>ABC Transport</TRANSPORTERNAME>")
            lines.append("<VEHICLENUMBER>MH12AB1234</VEHICLENUMBER>")
            lines.append("<DISTANCEINKM>250</DISTANCEINKM>")
        if guid == "guid-v-002":
            lines.append("<IRN>4B4C4D4E4F4G4H4I4J4K4L4M4N4O</IRN>")
            lines.append("<ACKNO>987654321</ACKNO>")
            lines.append("<ACKDT>20250405</ACKDT>")
            lines.append("<ISEINVOICE>Yes</ISEINVOICE>")
        lines.append(f"<NARRATION>Invoice {vnum}</NARRATION>")
        lines.append("<LEDGERENTRIES.LIST>")
        lines.append(f"<LEDGERNAME>{party}</LEDGERNAME>")
        lines.append(f"<ISDEEMEDPOSITIVE>{is_deemed_positive}</ISDEEMEDPOSITIVE>")
        lines.append(
            f"<AMOUNT>{'-' if is_deemed_positive == 'No' else ''}{amount}</AMOUNT>"
        )
        if guid == "guid-v-001":
            lines.append("<BILLALLOCATIONS.LIST>")
            lines.append("<BILLTYPE>New Ref</BILLTYPE>")
            lines.append(f"<NAME>{vnum}</NAME>")
            lines.append(f"<AMOUNT>{amount}</AMOUNT>")
            lines.append("<BILLCREDITPERIOD>")
            lines.append("<INDAYS>30</INDAYS>")
            lines.append("<INTEXT>30 Days</INTEXT>")
            lines.append("</BILLCREDITPERIOD>")
            lines.append("</BILLALLOCATIONS.LIST>")
        if guid == "guid-v-002":
            lines.append("<BILLALLOCATIONS.LIST>")
            lines.append("<BILLTYPE>New Ref</BILLTYPE>")
            lines.append(f"<NAME>{vnum}</NAME>")
            lines.append(f"<AMOUNT>{amount}</AMOUNT>")
            lines.append("</BILLALLOCATIONS.LIST>")
        lines.append("</LEDGERENTRIES.LIST>")
        if vtype in ("Sales", "Purchase"):
            lines.append("<LEDGERENTRIES.LIST>")
            lines.append(
                f"<LEDGERNAME>"
                f"{'Sales' if vtype == 'Sales' else 'Purchase'}</LEDGERNAME>"
            )
            lines.append(
                f"<ISDEEMEDPOSITIVE>"
                f"{'No' if vtype == 'Sales' else 'Yes'}</ISDEEMEDPOSITIVE>"
            )
            lines.append(f"<AMOUNT>{'-' if vtype == 'Sales' else ''}{amount}</AMOUNT>")
            if guid == "guid-v-004":
                lines.append("<COSTCENTRE.LIST>")
                lines.append("<COSTCENTRENAME>Head Office</COSTCENTRENAME>")
                lines.append(f"<AMOUNT>{amount}</AMOUNT>")
                lines.append("</COSTCENTRE.LIST>")
            lines.append("</LEDGERENTRIES.LIST>")
            if vtype == "Sales":
                lines.append("<LEDGERENTRIES.LIST>")
                lines.append("<LEDGERNAME>CGST</LEDGERNAME>")
                lines.append("<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>")
                lines.append(
                    f"<AMOUNT>-{(Decimal(amount) * Decimal('0.09')):.2f}</AMOUNT>"
                )
                lines.append("</LEDGERENTRIES.LIST>")
                lines.append("<LEDGERENTRIES.LIST>")
                lines.append("<LEDGERNAME>SGST</LEDGERNAME>")
                lines.append("<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>")
                lines.append(
                    f"<AMOUNT>-{(Decimal(amount) * Decimal('0.09')):.2f}</AMOUNT>"
                )
                lines.append("</LEDGERENTRIES.LIST>")
        if vtype in ("Sales", "Purchase") and guid in ("guid-v-001", "guid-v-002"):
            lines.append("<INVENTORYENTRIES.LIST>")
            lines.append("<STOCKITEMNAME>Widget A</STOCKITEMNAME>")
            lines.append("<ACTUALQTY>10 Nos</ACTUALQTY>")
            lines.append(f"<RATE>{amount[:-3] if '.' in amount else amount}/Nos</RATE>")
            lines.append(f"<AMOUNT>{amount}</AMOUNT>")
            lines.append("</INVENTORYENTRIES.LIST>")
        lines.append("</VOUCHER>")
    lines.append("</TALLYMESSAGE></DATA></BODY></ENVELOPE>")
    return "".join(lines)


def build_voucher_xml_all_ledger(
    vouchers: list | None = None,
) -> str:
    """Return Tally-format XML using ALLLEDGERENTRIES.LIST tags.

    TallyPrime uses ALLLEDGERENTRIES.LIST for the complete list of ledger
    entries in a voucher, while LEDGERENTRIES.LIST may only return a subset
    depending on context. Both tags should be handled by the parser.
    """
    vouchers = vouchers or SAMPLE_VOUCHERS_ALL_LEDGER
    lines = ["<ENVELOPE><BODY><DATA><TALLYMESSAGE>"]
    for (
        guid,
        alter_id,
        vtype,
        vdate,
        eff_date,
        party,
        vnum,
        amount,
        is_cancelled,
        is_void,
        is_postdated,
        entered_by,
    ) in vouchers:
        is_deemed_positive = "Yes" if vtype in ("Sales", "Payment") else "No"
        lines.append(f'<VOUCHER VCHTYPE="{vtype}" GUID="{guid}">')
        lines.append(f"<ALTERID>{alter_id}</ALTERID>")
        lines.append(f"<DATE>{vdate}</DATE>")
        lines.append(f"<EFFECTIVEDATE>{eff_date}</EFFECTIVEDATE>")
        lines.append(f"<VOUCHERNUMBER>{vnum}</VOUCHERNUMBER>")
        lines.append(f"<VOUCHERTYPENAME>{vtype}</VOUCHERTYPENAME>")
        lines.append(f"<PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>")
        lines.append(f"<ISCANCELLED>{'Yes' if is_cancelled else 'No'}</ISCANCELLED>")
        lines.append("<ISOPTIONAL>No</ISOPTIONAL>")
        lines.append(f"<ISPOSTDATED>{'Yes' if is_postdated else 'No'}</ISPOSTDATED>")
        lines.append(f"<ISVOID>{'Yes' if is_void else 'No'}</ISVOID>")
        lines.append(f"<ENTEREDBY>{entered_by}</ENTEREDBY>")
        lines.append(f"<NARRATION>Invoice {vnum}</NARRATION>")
        lines.append("<ALLLEDGERENTRIES.LIST>")
        lines.append(f"<LEDGERNAME>{party}</LEDGERNAME>")
        lines.append(f"<ISDEEMEDPOSITIVE>{is_deemed_positive}</ISDEEMEDPOSITIVE>")
        lines.append(
            f"<AMOUNT>{'-' if is_deemed_positive == 'No' else ''}{amount}</AMOUNT>"
        )
        lines.append("<BILLALLOCATIONS.LIST>")
        lines.append("<BILLTYPE>New Ref</BILLTYPE>")
        lines.append(f"<NAME>{vnum}</NAME>")
        lines.append(f"<AMOUNT>{amount}</AMOUNT>")
        lines.append("<BILLCREDITPERIOD>")
        lines.append("<INDAYS>45</INDAYS>")
        lines.append("<INTEXT>45 Days</INTEXT>")
        lines.append("<DUEONDATE>20250530</DUEONDATE>")
        lines.append("</BILLCREDITPERIOD>")
        lines.append("</BILLALLOCATIONS.LIST>")
        lines.append("</ALLLEDGERENTRIES.LIST>")
        lines.append("<ALLLEDGERENTRIES.LIST>")
        lines.append("<LEDGERNAME>Sales</LEDGERNAME>")
        lines.append("<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>")
        lines.append(f"<AMOUNT>-{amount}</AMOUNT>")
        lines.append("</ALLLEDGERENTRIES.LIST>")
        lines.append("<ALLLEDGERENTRIES.LIST>")
        lines.append("<LEDGERNAME>CGST</LEDGERNAME>")
        lines.append("<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>")
        lines.append(f"<AMOUNT>-{(Decimal(amount) * Decimal('0.09')):.2f}</AMOUNT>")
        lines.append("</ALLLEDGERENTRIES.LIST>")
        lines.append("<ALLLEDGERENTRIES.LIST>")
        lines.append("<LEDGERNAME>SGST</LEDGERNAME>")
        lines.append("<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>")
        lines.append(f"<AMOUNT>-{(Decimal(amount) * Decimal('0.09')):.2f}</AMOUNT>")
        lines.append("</ALLLEDGERENTRIES.LIST>")
        lines.append("<ALLINVENTORYENTRIES.LIST>")
        lines.append("<STOCKITEMNAME>Widget A</STOCKITEMNAME>")
        lines.append("<ACTUALQTY>10 Nos</ACTUALQTY>")
        lines.append(f"<RATE>{amount[:-3] if '.' in amount else amount}/Nos</RATE>")
        lines.append(f"<AMOUNT>{amount}</AMOUNT>")
        lines.append("</ALLINVENTORYENTRIES.LIST>")
        lines.append("</VOUCHER>")
    lines.append("</TALLYMESSAGE></DATA></BODY></ENVELOPE>")
    return "".join(lines)


SAMPLE_LEDGERS_JSON: dict[str, Any] = {
    "status": "1",
    "data": {
        "tallymessage": [
            {
                "ledger": {
                    "name": "Cash",
                    "guid": "guid-cash-001",
                    "alterid": "100",
                    "parent": "Cash-in-Hand",
                    "openingbalance": "0.00 Dr",
                    "closingbalance": "45000.00 Dr",
                    "isrevenue": "No",
                    "affectsgrossprofit": "No",
                    "ledmailingname": "Cash",
                }
            },
            {
                "ledger": {
                    "name": "HDFC Bank",
                    "guid": "guid-hdfc-001",
                    "alterid": "101",
                    "parent": "Bank Accounts",
                    "openingbalance": "0.00 Dr",
                    "closingbalance": "250000.00 Dr",
                    "isrevenue": "No",
                    "affectsgrossprofit": "No",
                    "ledmailingname": "HDFC Bank",
                }
            },
            {
                "ledger": {
                    "name": "Sales",
                    "guid": "guid-sales-001",
                    "alterid": "103",
                    "parent": "Sales Accounts",
                    "openingbalance": "0.00 Cr",
                    "closingbalance": "850000.00 Cr",
                    "isrevenue": "Yes",
                    "affectsgrossprofit": "No",
                    "gstin": "",
                    "ledmailingname": "Sales",
                }
            },
        ]
    },
}

SAMPLE_GROUPS_JSON: dict[str, Any] = {
    "status": "1",
    "data": {
        "tallymessage": [
            {
                "group": {
                    "name": "Sundry Debtors",
                    "guid": "guid-grp-001",
                    "alterid": "10",
                    "parent": "Current Assets",
                    "primarygroup": "Assets",
                    "isrevenue": "No",
                    "affectsgrossprofit": "No",
                    "netdebitcredit": "Dr",
                }
            },
            {
                "group": {
                    "name": "Sundry Creditors",
                    "guid": "guid-grp-002",
                    "alterid": "11",
                    "parent": "Current Liabilities",
                    "primarygroup": "Liabilities",
                    "isrevenue": "No",
                    "affectsgrossprofit": "No",
                    "netdebitcredit": "Cr",
                }
            },
        ]
    },
}

SAMPLE_STOCK_ITEMS_JSON: dict[str, Any] = {
    "status": "1",
    "data": {
        "tallymessage": [
            {
                "stockitem": {
                    "name": "Widget A",
                    "guid": "guid-item-001",
                    "alterid": "200",
                    "parent": "Stock-in-Trade",
                    "baseunits": "Nos",
                    "gstrate": "18.00",
                    "hsncode": "8471",
                    "closingbalance": "150 Nos",
                    "closingvalue": "45000.00",
                }
            },
        ]
    },
}

SAMPLE_VOUCHERS_JSON: dict[str, Any] = {
    "status": "1",
    "data": {
        "tallymessage": [
            {
                "voucher": {
                    "guid": "guid-v-001",
                    "alterid": "500",
                    "date": "20250401",
                    "effectivedate": "20250401",
                    "vouchernumber": "SI/001/25",
                    "vouchertypename": "Sales",
                    "partyledgername": "Sharma Trading Co",
                    "iscancelled": "No",
                    "isoptional": "No",
                    "ispostdated": "No",
                    "isvoid": "No",
                    "enteredby": "Admin",
                    "narration": "Invoice SI/001/25",
                    "allledgerentries.list": [
                        {
                            "ledgername": "Sharma Trading Co",
                            "amount": "50000.00",
                        },
                        {
                            "ledgername": "Sales",
                            "amount": "-50000.00",
                        },
                        {
                            "ledgername": "CGST",
                            "amount": "-4500.00",
                        },
                        {
                            "ledgername": "SGST",
                            "amount": "-4500.00",
                        },
                    ],
                }
            },
            {
                "voucher": {
                    "guid": "guid-v-002",
                    "alterid": "501",
                    "date": "20250405",
                    "effectivedate": "20250405",
                    "vouchernumber": "SI/002/25",
                    "vouchertypename": "Sales",
                    "partyledgername": "Patel Enterprises",
                    "iscancelled": "No",
                    "isoptional": "No",
                    "ispostdated": "No",
                    "isvoid": "No",
                    "enteredby": "Admin",
                    "narration": "Invoice SI/002/25",
                    "allledgerentries.list": [
                        {
                            "ledgername": "Patel Enterprises",
                            "amount": "35000.00",
                        },
                        {
                            "ledgername": "Sales",
                            "amount": "-35000.00",
                        },
                    ],
                }
            },
        ]
    },
}

SAMPLE_UNITS_JSON: dict[str, Any] = {
    "status": "1",
    "data": {
        "tallymessage": [
            {
                "unit": {
                    "name": "Nos",
                    "guid": "guid-unit-001",
                    "alterid": "300",
                    "unittype": "Simple",
                    "baseunits": "Nos",
                    "decimalplaces": "0",
                }
            },
        ]
    },
}

SAMPLE_STOCK_GROUPS_JSON: dict[str, Any] = {
    "status": "1",
    "data": {
        "tallymessage": [
            {
                "stockgroup": {
                    "name": "Stock-in-Trade",
                    "guid": "guid-sg-001",
                    "alterid": "310",
                    "parent": "Primary",
                    "shouldquantitiesadd": "Yes",
                }
            },
        ]
    },
}

SAMPLE_COST_CENTERS_JSON: dict[str, Any] = {
    "status": "1",
    "data": {
        "tallymessage": [
            {
                "costcentre": {
                    "name": "Head Office",
                    "guid": "guid-cc-001",
                    "alterid": "400",
                    "parent": "Primary",
                    "costcentretype": "Primary",
                }
            },
        ]
    },
}

SAMPLE_GODOWNS_JSON: dict[str, Any] = {
    "status": "1",
    "data": {
        "tallymessage": [
            {
                "godown": {
                    "name": "Main Store",
                    "guid": "guid-gd-001",
                    "alterid": "410",
                    "parent": "",
                }
            },
        ]
    },
}

SAMPLE_VOUCHER_TYPES_JSON: dict[str, Any] = {
    "status": "1",
    "data": {
        "tallymessage": [
            {
                "vouchertype": {
                    "name": "Sales",
                    "guid": "guid-vt-001",
                    "alterid": "400",
                    "parent": "Accounting Vouchers",
                }
            },
        ]
    },
}


def setup_mock_routes(httpserver) -> None:
    """Register all route handlers on the httpserver instance."""

    def _handler(request):
        content_type = request.headers.get("Content-Type", "")

        if content_type.lower().startswith("application/json"):
            return _json_handler(request)

        if request.headers.get("X-Tally-Simulate-Error") == "true":
            body = (
                "<ENVELOPE><BODY><DATA><LINEERROR>"
                "Company not loaded</LINEERROR>"
                "</DATA></BODY></ENVELOPE>"
            )
            return Response(body.encode("utf-8"), content_type="text/xml;charset=utf-8")

        if "utf-16" in content_type.lower():
            response_encoding = "utf-16-le"
            response_ct = "text/xml;charset=utf-16"
        else:
            response_encoding = "utf-8"
            response_ct = "text/xml;charset=utf-8"

        xml_body = request.data.decode(response_encoding, errors="replace")

        if ">Group<" in xml_body:
            resp_xml = build_group_xml()
        elif ">Ledger<" in xml_body:
            resp_xml = build_ledger_xml()
        elif ">VoucherType<" in xml_body:
            resp_xml = build_voucher_type_xml()
        elif ">Unit<" in xml_body:
            resp_xml = build_unit_xml()
        elif ">StockGroup<" in xml_body:
            resp_xml = build_stock_group_xml()
        elif ">StockItem<" in xml_body:
            resp_xml = build_stock_item_xml()
        elif ">CostCentre<" in xml_body:
            resp_xml = build_cost_center_xml()
        elif ">Godown<" in xml_body:
            resp_xml = build_godown_xml()
        elif "GSTR 2A" in xml_body:
            resp_xml = (
                "<ENVELOPE><BODY><DATA>"
                "<DSPACCINFO>"
                "<PARTYGSTIN>27AAACM2850K1Z1</PARTYGSTIN>"
                "<PARTYNAME>Mehta Suppliers</PARTYNAME>"
                "<VOUCHERNUMBER>PI/001/25</VOUCHERNUMBER>"
                "<DATE>20250403</DATE>"
                "<TAXABLEVALUE>42000</TAXABLEVALUE>"
                "<CGSTAMT>3780</CGSTAMT>"
                "<SGSTAMT>3780</SGSTAMT>"
                "<IGSTAMT>0</IGSTAMT>"
                "<CESSAMT>0</CESSAMT>"
                "<ITCAVAILABLE>7560</ITCAVAILABLE>"
                "<SUPPLYTYPE>Regular</SUPPLYTYPE>"
                "</DSPACCINFO>"
                "</DATA></BODY></ENVELOPE>"
            )
        elif "GSTR 9" in xml_body:
            resp_xml = (
                "<ENVELOPE><BODY><DATA>"
                "<DSPDISPNAME>4. Taxable outward supplies</DSPDISPNAME>"
                "<DSPACCINFO>"
                "<TAXABLEVALUE>850000</TAXABLEVALUE>"
                "<IGSTAMT>0</IGSTAMT>"
                "<CGSTAMT>76500</CGSTAMT>"
                "<SGSTAMT>76500</SGSTAMT>"
                "<CESSAMT>0</CESSAMT>"
                "</DSPACCINFO>"
                "<DSPDISPNAME>5. Exempt supplies</DSPDISPNAME>"
                "<DSPACCINFO>"
                "<TAXABLEVALUE>50000</TAXABLEVALUE>"
                "<IGSTAMT>0</IGSTAMT>"
                "<CGSTAMT>0</CGSTAMT>"
                "<SGSTAMT>0</SGSTAMT>"
                "<CESSAMT>0</CESSAMT>"
                "</DSPACCINFO>"
                "</DATA></BODY></ENVELOPE>"
            )
        elif ">Voucher<" in xml_body:
            resp_xml = build_voucher_xml()
        elif "Import Data" in xml_body:
            if ">All Masters<" in xml_body or "<LEDGER" in xml_body:
                resp_xml = (
                    "<ENVELOPE><HEADER><VERSION>1</VERSION>"
                    "<STATUS>1</STATUS></HEADER>"
                    "<BODY><DATA><IMPORTRESULT>"
                    "<CREATED>1</CREATED><ALTERED>0</ALTERED>"
                    "<DELETED>0</DELETED><ERRORS>0</ERRORS>"
                    "</IMPORTRESULT></DATA></BODY></ENVELOPE>"
                )
            elif ">Vouchers<" in xml_body or "<VOUCHER" in xml_body:
                resp_xml = (
                    "<ENVELOPE><HEADER><VERSION>1</VERSION>"
                    "<STATUS>1</STATUS></HEADER>"
                    "<BODY><DATA><IMPORTRESULT>"
                    "<CREATED>1</CREATED><ALTERED>0</ALTERED>"
                    "<DELETED>0</DELETED><ERRORS>0</ERRORS>"
                    "</IMPORTRESULT></DATA></BODY></ENVELOPE>"
                )
            else:
                resp_xml = (
                    "<ENVELOPE><HEADER><VERSION>1</VERSION>"
                    "<STATUS>1</STATUS></HEADER>"
                    "<BODY><DATA><IMPORTRESULT>"
                    "<CREATED>0</CREATED><ALTERED>0</ALTERED>"
                    "<DELETED>0</DELETED><ERRORS>0</ERRORS>"
                    "</IMPORTRESULT></DATA></BODY></ENVELOPE>"
                )
        else:
            resp_xml = "<ENVELOPE><BODY><DATA></DATA></BODY></ENVELOPE>"

        return Response(resp_xml.encode(response_encoding), content_type=response_ct)

    def _json_handler(request):
        tally_type = request.headers.get("type", "").lower()
        subtype = request.headers.get("subtype", "").lower()
        tally_id = request.headers.get("id", "")

        if request.headers.get("X-Tally-Simulate-Error") == "true":
            return Response(
                json.dumps({"status": "-1", "error": "Company not loaded"}),
                content_type="application/json",
            )

        if tally_type == "collection":
            if "ledger" in tally_id.lower():
                resp = SAMPLE_LEDGERS_JSON
            elif "group" in tally_id.lower():
                resp = SAMPLE_GROUPS_JSON
            elif "stockitem" in tally_id.lower():
                resp = SAMPLE_STOCK_ITEMS_JSON
            elif "stockgroup" in tally_id.lower():
                resp = SAMPLE_STOCK_GROUPS_JSON
            elif "unit" in tally_id.lower():
                resp = SAMPLE_UNITS_JSON
            elif "costcentre" in tally_id.lower():
                resp = SAMPLE_COST_CENTERS_JSON
            elif "godown" in tally_id.lower():
                resp = SAMPLE_GODOWNS_JSON
            elif "vouchertype" in tally_id.lower():
                resp = SAMPLE_VOUCHER_TYPES_JSON
            elif "voucher" in tally_id.lower():
                resp = SAMPLE_VOUCHERS_JSON
            else:
                try:
                    body = json.loads(request.data.decode("utf-8"))
                    tdl_messages = body.get("tdlmessage", [])
                    for msg in tdl_messages:
                        coll = msg.get("collection", {})
                        t = coll.get("type", "").lower()
                        if "ledger" in t:
                            resp = SAMPLE_LEDGERS_JSON
                            break
                        elif "group" in t:
                            resp = SAMPLE_GROUPS_JSON
                            break
                        elif "stockitem" in t:
                            resp = SAMPLE_STOCK_ITEMS_JSON
                            break
                        elif "stockgroup" in t:
                            resp = SAMPLE_STOCK_GROUPS_JSON
                            break
                        elif "unit" in t:
                            resp = SAMPLE_UNITS_JSON
                            break
                        elif "costcentre" in t:
                            resp = SAMPLE_COST_CENTERS_JSON
                            break
                        elif "godown" in t:
                            resp = SAMPLE_GODOWNS_JSON
                            break
                        elif "vouchertype" in t:
                            resp = SAMPLE_VOUCHER_TYPES_JSON
                            break
                        elif "voucher" in t:
                            resp = SAMPLE_VOUCHERS_JSON
                            break
                    else:
                        resp = {"status": "1", "data": {"tallymessage": []}}
                except (json.JSONDecodeError, ValueError):
                    resp = {"status": "1", "data": {"tallymessage": []}}
        elif tally_type == "object":
            if "ledger" in subtype:
                resp = {
                    "status": "1",
                    "data": {
                        "tallymessage": SAMPLE_LEDGERS_JSON["data"]["tallymessage"][0]
                    },
                }
            elif "group" in subtype:
                resp = {
                    "status": "1",
                    "data": {
                        "tallymessage": SAMPLE_GROUPS_JSON["data"]["tallymessage"][0]
                    },
                }
            elif "voucher" in subtype:
                resp = {
                    "status": "1",
                    "data": {
                        "tallymessage": SAMPLE_VOUCHERS_JSON["data"]["tallymessage"][0]
                    },
                }
            else:
                resp = {"status": "1", "data": {"tallymessage": {}}}
        elif tally_type == "data":
            tally_request = request.headers.get("tallyrequest", "").lower()
            if tally_request == "import":
                resp = {
                    "status": "1",
                    "cmp_info": {
                        "created": 1,
                        "altered": 0,
                        "deleted": 0,
                        "errors": 0,
                    },
                }
            else:
                resp = {
                    "status": "1",
                    "data": {
                        "tallymessage": [
                            {
                                "gstr2a": {
                                    "partygstin": "27AAACM2850K1Z1",
                                    "partyname": "Mehta Suppliers",
                                    "vouchernumber": "PI/001/25",
                                    "date": "20250403",
                                    "taxablevalue": "42000",
                                    "centraltax": "3780",
                                    "statetax": "3780",
                                    "integratedtax": "0",
                                    "cess": "0",
                                    "itcavailable": "7560",
                                    "supplytype": "Regular",
                                }
                            }
                        ]
                    },
                }
        else:
            resp = {"status": "1", "data": {}}

        return Response(
            json.dumps(resp),
            content_type="application/json",
        )

    httpserver.expect_request("/").respond_with_handler(_handler)
