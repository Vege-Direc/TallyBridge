"""Tally XML/JSON parser — see SPECS.md §5."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from tallybridge.models.report import GSTR1Section, GSTR3BSection

from tallybridge.models.master import (
    TallyCostCenter,
    TallyGodown,
    TallyGroup,
    TallyLedger,
    TallyStockGroup,
    TallyStockItem,
    TallyUnit,
    TallyVoucherType,
)
from tallybridge.models.report import (
    OutstandingBill,
    ReportLine,
    TallyReport,
    TrialBalanceLine,
)
from tallybridge.models.voucher import (
    TallyBillAllocation,
    TallyCostCentreAllocation,
    TallyInventoryEntry,
    TallyVoucher,
    TallyVoucherEntry,
)


class TallyXMLParser:
    CURRENCY_ENTITY_FIXES: dict[str, str] = {
        "&#8387;": "\u20c3",
        "&#8385;": "\u20c1",
    }

    @staticmethod
    def _fix_currency_entities(xml: str) -> str:
        """Replace known TallyPrime 7.0 currency entity codes in XML.

        TallyPrime 7.0 introduced AED (U+20C3) and SAR (U+20C1) currency
        symbols. Their XML entity codes (&#8387; and &#8385;) may not
        decode correctly in all XML parsers. Pre-replace them to ensure
        correct handling.
        """
        for entity, replacement in TallyXMLParser.CURRENCY_ENTITY_FIXES.items():
            xml = xml.replace(entity, replacement)
        return xml

    @staticmethod
    def parse_amount(amount_str: str | None) -> Decimal:
        """Parse Tally amount string to signed Decimal.

        "1234.56 Dr"  -> Decimal("1234.56")
        "1234.56 Cr"  -> Decimal("-1234.56")
        "-500.00"     -> Decimal("-500.00")
        "" or None    -> Decimal("0")

        On any parse failure: log warning, return Decimal("0").
        """
        if not amount_str or not amount_str.strip():
            return Decimal("0")
        amount_str = amount_str.strip()
        sign = Decimal("1")
        if amount_str.endswith("Cr"):
            sign = Decimal("-1")
            amount_str = amount_str[:-2].strip()
        elif amount_str.endswith("Dr"):
            amount_str = amount_str[:-2].strip()
        try:
            return Decimal(amount_str) * sign
        except (InvalidOperation, ValueError) as exc:
            logger.warning("Failed to parse amount '{}': {}", amount_str, exc)
            return Decimal("0")

    @staticmethod
    def parse_date(date_str: str | None) -> date | None:
        """Parse Tally YYYYMMDD to Python date. Returns None on failure."""
        if not date_str or not date_str.strip():
            return None
        date_str = date_str.strip()
        try:
            return date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
        except (ValueError, IndexError) as exc:
            logger.warning("Failed to parse date '{}': {}", date_str, exc)
            return None

    @staticmethod
    def parse_bool(bool_str: str | None) -> bool:
        """'Yes' -> True, anything else -> False."""
        return bool_str is not None and bool_str.strip().lower() == "yes"

    @staticmethod
    def get_text(element: ET.Element | None, tag: str, default: str = "") -> str:
        """Safely get text from a child tag or attribute.
        Returns default if missing."""
        if element is None:
            return default
        child = element.find(tag)
        if child is not None and child.text is not None:
            return child.text
        attrib_val = element.get(tag)
        if attrib_val is not None:
            return attrib_val
        return default

    def parse_ledgers(self, xml: str) -> list[TallyLedger]:
        """Parse ledger collection XML."""
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            logger.warning("Failed to parse ledger XML: {}", exc)
            return []

        ledgers: list[TallyLedger] = []
        for elem in root.iter("LEDGER"):
            try:
                ledger = TallyLedger(
                    name=self.get_text(elem, "NAME"),
                    guid=self.get_text(elem, "GUID"),
                    alter_id=int(self.get_text(elem, "ALTERID", "0")),
                    parent_group=self.get_text(elem, "PARENT"),
                    opening_balance=self.parse_amount(
                        self.get_text(elem, "OPENINGBALANCE")
                    ),
                    closing_balance=self.parse_amount(
                        self.get_text(elem, "CLOSINGBALANCE")
                    ),
                    is_revenue=self.parse_bool(self.get_text(elem, "ISREVENUE")),
                    affects_gross_profit=self.parse_bool(
                        self.get_text(elem, "AFFECTSGROSSPROFIT")
                    ),
                    gstin=self.get_text(elem, "GSTIN") or None,
                    party_name=self.get_text(elem, "LEDMAILINGNAME") or None,
                )
                ledgers.append(ledger)
            except Exception as exc:
                logger.warning("Failed to parse ledger element: {}", exc)
        return ledgers

    def parse_groups(self, xml: str) -> list[TallyGroup]:
        """Parse group collection XML."""
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            logger.warning("Failed to parse group XML: {}", exc)
            return []

        groups: list[TallyGroup] = []
        for elem in root.iter("GROUP"):
            try:
                group = TallyGroup(
                    name=self.get_text(elem, "NAME"),
                    guid=self.get_text(elem, "GUID"),
                    alter_id=int(self.get_text(elem, "ALTERID", "0")),
                    parent=self.get_text(elem, "PARENT"),
                    primary_group=self.get_text(elem, "PRIMARYGROUP"),
                    is_revenue=self.parse_bool(self.get_text(elem, "ISREVENUE")),
                    affects_gross_profit=self.parse_bool(
                        self.get_text(elem, "AFFECTSGROSSPROFIT")
                    ),
                    net_debit_credit=self.get_text(elem, "NETDEBITCREDIT", "Dr"),
                )
                groups.append(group)
            except Exception as exc:
                logger.warning("Failed to parse group element: {}", exc)
        return groups

    def parse_stock_items(self, xml: str) -> list[TallyStockItem]:
        """Parse stock item collection XML."""
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            logger.warning("Failed to parse stock item XML: {}", exc)
            return []

        items: list[TallyStockItem] = []
        for elem in root.iter("STOCKITEM"):
            try:
                closing_balance_text = self.get_text(elem, "CLOSINGBALANCE")
                closing_qty = self.parse_quantity(closing_balance_text)
                stock_item = TallyStockItem(
                    name=self.get_text(elem, "NAME"),
                    guid=self.get_text(elem, "GUID"),
                    alter_id=int(self.get_text(elem, "ALTERID", "0")),
                    parent_group=self.get_text(elem, "PARENT"),
                    unit=self.get_text(elem, "BASEUNITS"),
                    gst_rate=self.parse_amount(self.get_text(elem, "GSTRATE")) or None,
                    hsn_code=self.get_text(elem, "HSNCODE") or None,
                    closing_quantity=closing_qty,
                    closing_value=self.parse_amount(
                        self.get_text(elem, "CLOSINGVALUE")
                    ),
                )
                items.append(stock_item)
            except Exception as exc:
                logger.warning("Failed to parse stock item element: {}", exc)
        return items

    def parse_voucher_types(self, xml: str) -> list[TallyVoucherType]:
        """Parse voucher type collection XML."""
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            logger.warning("Failed to parse voucher type XML: {}", exc)
            return []

        vtypes: list[TallyVoucherType] = []
        for elem in root.iter("VOUCHERTYPE"):
            try:
                vtype = TallyVoucherType(
                    name=self.get_text(elem, "NAME"),
                    guid=self.get_text(elem, "GUID"),
                    alter_id=int(self.get_text(elem, "ALTERID", "0")),
                    parent=self.get_text(elem, "PARENT"),
                )
                vtypes.append(vtype)
            except Exception as exc:
                logger.warning("Failed to parse voucher type element: {}", exc)
        return vtypes

    def parse_units(self, xml: str) -> list[TallyUnit]:
        """Parse unit collection XML."""
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            logger.warning("Failed to parse unit XML: {}", exc)
            return []

        units: list[TallyUnit] = []
        for elem in root.iter("UNIT"):
            try:
                unit = TallyUnit(
                    name=self.get_text(elem, "NAME"),
                    guid=self.get_text(elem, "GUID"),
                    alter_id=int(self.get_text(elem, "ALTERID", "0")),
                    unit_type=self.get_text(elem, "UNITTYPE", "Simple"),
                    base_units=self.get_text(elem, "BASEUNITS") or None,
                    decimal_places=int(self.get_text(elem, "DECIMALPLACES", "0")),
                    symbol=self.get_text(elem, "SYMBOL") or None,
                )
                units.append(unit)
            except Exception as exc:
                logger.warning("Failed to parse unit element: {}", exc)
        return units

    def parse_stock_groups(self, xml: str) -> list[TallyStockGroup]:
        """Parse stock group collection XML."""
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            logger.warning("Failed to parse stock group XML: {}", exc)
            return []

        groups: list[TallyStockGroup] = []
        for elem in root.iter("STOCKGROUP"):
            try:
                sg = TallyStockGroup(
                    name=self.get_text(elem, "NAME"),
                    guid=self.get_text(elem, "GUID"),
                    alter_id=int(self.get_text(elem, "ALTERID", "0")),
                    parent=self.get_text(elem, "PARENT"),
                    should_quantities_add=self.parse_bool(
                        self.get_text(elem, "SHOULDQUANTITIESADD")
                    ),
                )
                groups.append(sg)
            except Exception as exc:
                logger.warning("Failed to parse stock group element: {}", exc)
        return groups

    def parse_cost_centers(self, xml: str) -> list[TallyCostCenter]:
        """Parse cost centre collection XML."""
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            logger.warning("Failed to parse cost centre XML: {}", exc)
            return []

        centers: list[TallyCostCenter] = []
        for elem in root.iter("COSTCENTRE"):
            try:
                cc = TallyCostCenter(
                    name=self.get_text(elem, "NAME"),
                    guid=self.get_text(elem, "GUID"),
                    alter_id=int(self.get_text(elem, "ALTERID", "0")),
                    parent=self.get_text(elem, "PARENT"),
                    email=self.get_text(elem, "EMAIL") or None,
                    cost_centre_type=self.get_text(elem, "COSTCENTRETYPE", "Primary"),
                )
                centers.append(cc)
            except Exception as exc:
                logger.warning("Failed to parse cost centre element: {}", exc)
        return centers

    def parse_godowns(self, xml: str) -> list[TallyGodown]:
        """Parse Godown collection XML into TallyGodown models."""
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            logger.warning("Failed to parse godown XML: {}", exc)
            return []

        godowns: list[TallyGodown] = []
        for elem in root.iter("GODOWN"):
            try:
                godown = TallyGodown(
                    name=self.get_text(elem, "NAME"),
                    guid=self.get_text(elem, "GUID"),
                    alter_id=int(self.get_text(elem, "ALTERID", "0")),
                    parent=self.get_text(elem, "PARENT") or None,
                )
                godowns.append(godown)
            except Exception as exc:
                logger.warning("Failed to parse godown element: {}", exc)
        return godowns

    def parse_vouchers(self, xml: str) -> list[TallyVoucher]:
        """Parse voucher collection XML.

        Each <VOUCHER> element contains:
        - Direct fields: GUID, ALTERID, DATE, VOUCHERNUMBER, VOUCHERTYPENAME, etc.
        - <LEDGERENTRIES.LIST> sub-elements with LEDGERNAME and AMOUNT
        - <INVENTORYENTRIES.LIST> sub-elements with
          STOCKITEMNAME, ACTUALQTY, RATE, AMOUNT
        """
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            logger.warning("Failed to parse voucher XML: {}", exc)
            return []

        vouchers: list[TallyVoucher] = []
        for elem in root.iter("VOUCHER"):
            try:
                ledger_entries = self._parse_ledger_entries(elem)
                inventory_entries = self._parse_inventory_entries(elem)
                cost_centre_allocations = self._parse_cost_centre_allocations(elem)
                bill_allocations = self._parse_bill_allocations(elem)
                total_amount = sum(
                    (e.amount for e in ledger_entries if e.amount > 0),
                    Decimal("0"),
                )
                gst_amount = sum(
                    (
                        e.amount
                        for e in ledger_entries
                        if "GST" in e.ledger_name.upper()
                    ),
                    Decimal("0"),
                )
                parsed_date = self.parse_date(self.get_text(elem, "DATE"))
                if parsed_date is None:
                    logger.warning(
                        "Skipping voucher with unparseable date: guid={}",
                        self.get_text(elem, "GUID"),
                    )
                    continue
                voucher = TallyVoucher(
                    guid=self.get_text(elem, "GUID"),
                    alter_id=int(self.get_text(elem, "ALTERID", "0")),
                    voucher_number=self.get_text(elem, "VOUCHERNUMBER"),
                    voucher_type=self.get_text(elem, "VOUCHERTYPENAME"),
                    date=parsed_date,
                    effective_date=self.parse_date(
                        self.get_text(elem, "EFFECTIVEDATE")
                    ),
                    reference=self.get_text(elem, "REFERENCE") or None,
                    narration=self.get_text(elem, "NARRATION") or None,
                    is_cancelled=self.parse_bool(self.get_text(elem, "ISCANCELLED")),
                    is_optional=self.parse_bool(self.get_text(elem, "ISOPTIONAL")),
                    is_postdated=self.parse_bool(self.get_text(elem, "ISPOSTDATED")),
                    is_void=self.parse_bool(self.get_text(elem, "ISVOID")),
                    party_ledger=self.get_text(elem, "PARTYLEDGERNAME") or None,
                    party_gstin=self.get_text(elem, "PARTYGSTIN") or None,
                    place_of_supply=self.get_text(elem, "PLACEOFSUPPLY") or None,
                    due_date=self.parse_date(self.get_text(elem, "BASICDUEDATEOFPYMT")),
                    entered_by=self.get_text(elem, "ENTEREDBY") or None,
                    ledger_entries=ledger_entries,
                    inventory_entries=inventory_entries,
                    cost_centre_allocations=cost_centre_allocations,
                    bill_allocations=bill_allocations,
                    total_amount=abs(total_amount),
                    gst_amount=abs(gst_amount),
                )
                vouchers.append(voucher)
            except Exception as exc:
                logger.warning("Failed to parse voucher element: {}", exc)
        return vouchers

    def parse_outstanding_bills(self, xml: str) -> list[OutstandingBill]:
        """Parse outstanding bills XML."""
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            logger.warning("Failed to parse outstanding XML: {}", exc)
            return []

        bills: list[OutstandingBill] = []
        for elem in root.iter("BILL"):
            try:
                parsed_bill_date = self.parse_date(self.get_text(elem, "DATE"))
                if parsed_bill_date is None:
                    logger.warning(
                        "Skipping bill with unparseable date: party={}",
                        self.get_text(elem, "PARTYNAME"),
                    )
                    continue
                bill = OutstandingBill(
                    party_name=self.get_text(elem, "PARTYNAME"),
                    bill_date=parsed_bill_date,
                    bill_number=self.get_text(elem, "BILLNUMBER"),
                    bill_amount=self.parse_amount(self.get_text(elem, "BILLAMOUNT")),
                    outstanding_amount=self.parse_amount(
                        self.get_text(elem, "OUTSTANDINGAMOUNT")
                    ),
                    voucher_type=self.get_text(elem, "VOUCHERTYPENAME", "Sales"),
                )
                bills.append(bill)
            except Exception as exc:
                logger.warning("Failed to parse bill element: {}", exc)
        return bills

    def _parse_ledger_entries(
        self, voucher_elem: ET.Element
    ) -> list[TallyVoucherEntry]:
        entries: list[TallyVoucherEntry] = []
        for entry in self._get_ledger_entry_elements(voucher_elem):
            name = self.get_text(entry, "LEDGERNAME")
            amount_text = self.get_text(entry, "AMOUNT")
            amount = self.parse_amount(amount_text)
            if amount == Decimal("0"):
                amount = self._parse_complex_amount(entry, "AMOUNT")
            entries.append(TallyVoucherEntry(ledger_name=name, amount=amount))
        return entries

    def _parse_inventory_entries(
        self, voucher_elem: ET.Element
    ) -> list[TallyInventoryEntry]:
        entries: list[TallyInventoryEntry] = []
        for entry in self._get_inventory_entry_elements(voucher_elem):
            name = self.get_text(entry, "STOCKITEMNAME")
            qty_text = self.get_text(entry, "ACTUALQTY")
            qty = self.parse_quantity(qty_text)
            rate = self.parse_rate(self.get_text(entry, "RATE"))
            amount = self.parse_amount(self.get_text(entry, "AMOUNT"))
            if amount == Decimal("0"):
                amount = self._parse_complex_amount(entry, "AMOUNT")
            godown = self.get_text(entry, "GODOWN") or None
            batch = self.get_text(entry, "BATCH") or None
            entries.append(
                TallyInventoryEntry(
                    stock_item_name=name,
                    quantity=qty,
                    rate=rate,
                    amount=amount,
                    godown=godown,
                    batch=batch,
                )
            )
        return entries

    @staticmethod
    def _get_ledger_entry_elements(voucher_elem: ET.Element) -> list[ET.Element]:
        """Get ledger entry elements, preferring ALLLEDGERENTRIES.LIST (TallyPrime).

        TallyPrime includes both LEDGERENTRIES.LIST (subset) and
        ALLLEDGERENTRIES.LIST (complete) in responses. Using both would
        duplicate entries. Prefer ALLLEDGERENTRIES.LIST; fall back to
        LEDGERENTRIES.LIST for Tally.ERP 9 compatibility.
        """
        all_entries = voucher_elem.findall("ALLLEDGERENTRIES.LIST")
        if all_entries:
            return all_entries
        return voucher_elem.findall("LEDGERENTRIES.LIST")

    @staticmethod
    def _get_inventory_entry_elements(
        voucher_elem: ET.Element,
    ) -> list[ET.Element]:
        """Get inventory entry elements, preferring ALLINVENTORYENTRIES.LIST.

        Same ALL* vs non-ALL pattern as ledger entries.
        """
        all_entries = voucher_elem.findall("ALLINVENTORYENTRIES.LIST")
        if all_entries:
            return all_entries
        return voucher_elem.findall("INVENTORYENTRIES.LIST")

    def _parse_cost_centre_allocations(
        self, voucher_elem: ET.Element
    ) -> list[TallyCostCentreAllocation]:
        """Extract cost centre allocations from ledger entries.

        Note: COSTCENTRE.LIST and CATEGORYALLOCATIONS.LIST only appear in
        Tally's XML response if the company has cost centres enabled
        (F11 > Inventory Features > Cost Centres). This is a functional
        limitation — if cost centres are not enabled in Tally, these
        sub-collections will simply not be present in the XML response.
        """
        allocations: list[TallyCostCentreAllocation] = []
        for entry in self._get_ledger_entry_elements(voucher_elem):
            ledger_name = self.get_text(entry, "LEDGERNAME")
            for cc_elem in entry.findall("COSTCENTRE.LIST"):
                cc_name = self.get_text(cc_elem, "COSTCENTRENAME")
                amount = self.parse_amount(self.get_text(cc_elem, "AMOUNT"))
                if amount == Decimal("0"):
                    amount = self._parse_complex_amount(cc_elem, "AMOUNT")
                allocations.append(
                    TallyCostCentreAllocation(
                        ledger_name=ledger_name,
                        cost_centre=cc_name,
                        amount=amount,
                    )
                )
            for cat_elem in entry.findall("CATEGORYALLOCATIONS.LIST"):
                for cc_elem in cat_elem.findall("COSTCENTRE.LIST"):
                    cc_name = self.get_text(cc_elem, "COSTCENTRENAME")
                    amount = self.parse_amount(self.get_text(cc_elem, "AMOUNT"))
                    if amount == Decimal("0"):
                        amount = self._parse_complex_amount(cc_elem, "AMOUNT")
                    allocations.append(
                        TallyCostCentreAllocation(
                            ledger_name=ledger_name,
                            cost_centre=cc_name,
                            amount=amount,
                        )
                    )
        return allocations

    def _parse_bill_allocations(
        self, voucher_elem: ET.Element
    ) -> list[TallyBillAllocation]:
        """Extract bill allocations from ledger entries.

        Note: BILLALLOCATIONS.LIST only appears in Tally's XML response if
        bill-wise breakup is enabled for the ledger's group (F11 > Accounting
        Features > Maintain Bill-wise Details). This is a functional
        limitation — if bill-wise breakup is not enabled, this sub-collection
        will not be present in the XML response.
        """
        allocations: list[TallyBillAllocation] = []
        for entry in self._get_ledger_entry_elements(voucher_elem):
            ledger_name = self.get_text(entry, "LEDGERNAME")
            for bill_elem in entry.findall("BILLALLOCATIONS.LIST"):
                bill_type = self.get_text(bill_elem, "BILLTYPE") or None
                bill_name = self.get_text(bill_elem, "NAME")
                amount = self.parse_amount(self.get_text(bill_elem, "AMOUNT"))
                if amount == Decimal("0"):
                    amount = self._parse_complex_amount(bill_elem, "AMOUNT")
                bill_credit_period = self._parse_bill_credit_period(bill_elem)
                allocations.append(
                    TallyBillAllocation(
                        ledger_name=ledger_name,
                        bill_name=bill_name,
                        amount=amount,
                        bill_type=bill_type,
                        bill_credit_period=bill_credit_period,
                    )
                )
        return allocations

    def _parse_complex_amount(self, parent: ET.Element, tag: str) -> Decimal:
        amount_elem = parent.find(tag)
        if amount_elem is None:
            return Decimal("0")
        inner = amount_elem.find("AMOUNT")
        if inner is not None and inner.text:
            return self.parse_amount(inner.text.strip())
        is_debit_elem = amount_elem.find("ISDEBIT")
        raw = (
            inner.text.strip() if inner is not None and inner.text else amount_elem.text
        )
        if raw and is_debit_elem is not None:
            val = self.parse_amount(raw)
            if is_debit_elem.text and is_debit_elem.text.strip().lower() == "false":
                val = -abs(val)
            return val
        return Decimal("0")

    @staticmethod
    def _parse_bill_credit_period(bill_elem: ET.Element) -> int | None:
        bcp = bill_elem.find("BILLCREDITPERIOD")
        if bcp is None:
            return None
        in_days = bcp.find("INDAYS")
        if in_days is not None and in_days.text:
            try:
                return int(in_days.text.strip())
            except ValueError:
                pass
        if bcp.text:
            try:
                return int(bcp.text.strip())
            except ValueError:
                pass
        due_on_date = bcp.find("DUEONDATE")
        if due_on_date is not None and due_on_date.text:
            date_val = TallyXMLParser.parse_date(due_on_date.text.strip())
            if date_val is not None:
                bill_date_elem = bill_elem.find("BILLDATE")
                if bill_date_elem is not None and bill_date_elem.text:
                    bill_date = TallyXMLParser.parse_date(bill_date_elem.text.strip())
                    if bill_date is not None:
                        return (date_val - bill_date).days
        return None

    @staticmethod
    def parse_quantity(qty_str: str | None) -> Decimal:
        """Parse Tally quantity string like '5 Nos' or '-10 Kgs' to Decimal."""
        if not qty_str or not qty_str.strip():
            return Decimal("0")
        parts = qty_str.strip().split()
        try:
            return Decimal(parts[0])
        except (InvalidOperation, ValueError, IndexError) as exc:
            logger.warning("Failed to parse quantity '{}': {}", qty_str, exc)
            return Decimal("0")

    @staticmethod
    def parse_rate(rate_str: str | None) -> Decimal:
        """Parse Tally rate string like '15000.00/Nos' to Decimal."""
        if not rate_str or not rate_str.strip():
            return Decimal("0")
        try:
            return Decimal(rate_str.strip().split("/")[0])
        except (InvalidOperation, ValueError, IndexError) as exc:
            logger.warning("Failed to parse rate '{}': {}", rate_str, exc)
            return Decimal("0")

    @staticmethod
    def parse_report(
        xml_str: str,
        report_name: str = "Unknown",
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> TallyReport:
        """Parse a Tally TYPE=Data report response into a TallyReport.

        Detects the report type from ``report_name`` and delegates to
        the appropriate specialist parser.  Returns a ``TallyReport``
        with the structured data.

        Args:
            xml_str: Raw XML response from Tally.
            report_name: The report ID that was requested (e.g. "Balance
                Sheet").
            from_date: Start date of the report period.
            to_date: End date of the report period.
        """
        from tallybridge.models.report import (
            TallyReportType,
        )

        report_type: TallyReportType = "Unknown"
        if "balance sheet" in report_name.lower():
            report_type = "Balance Sheet"
        elif "profit" in report_name.lower():
            report_type = "Profit & Loss"
        elif "trial balance" in report_name.lower():
            report_type = "Trial Balance"
        elif "day book" in report_name.lower():
            report_type = "Day Book"

        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as exc:
            logger.warning("Failed to parse report XML: {}", exc)
            return TallyReport(
                report_type=report_type,
                from_date=from_date,
                to_date=to_date,
            )

        if report_type == "Trial Balance":
            tb_lines = TallyXMLParser._parse_trial_balance_report(root)
            return TallyReport(
                report_type=report_type,
                from_date=from_date,
                to_date=to_date,
                trial_balance=tb_lines,
            )

        if report_type == "Day Book":
            vouchers = TallyXMLParser._parse_day_book_report(root)
            return TallyReport(
                report_type=report_type,
                from_date=from_date,
                to_date=to_date,
                vouchers=vouchers,
            )

        if report_type in ("Balance Sheet", "Profit & Loss"):
            name_tag = "BSNAME" if report_type == "Balance Sheet" else "PLNAME"
            amt_tag = "BSCLOSAMT" if report_type == "Balance Sheet" else "PLCLOSAMT"
            bs_lines = TallyXMLParser._parse_bs_pl_report(root, name_tag, amt_tag)
            return TallyReport(
                report_type=report_type,
                from_date=from_date,
                to_date=to_date,
                lines=bs_lines,
            )

        return TallyReport(
            report_type=report_type,
            from_date=from_date,
            to_date=to_date,
        )

    @staticmethod
    def _parse_bs_pl_report(
        root: ET.Element,
        name_tag: str,
        amt_tag: str,
    ) -> list[ReportLine]:
        """Parse Balance Sheet or P&L report groups.

        Tally returns repeated ``<BSNAME>/<BSCLOSAMT>`` (or
        ``<PLNAME>/<PLCLOSAMT>``) groups at the ENVELOPE level.  Each
        name-group contains ``<DSPDISPNAME>`` and each amount-group
        contains ``<DSPCLDRAMTA>`` / ``<DSPCLCRAMTA>``.
        """
        names: list[str] = []
        debits: list[Decimal] = []
        credits: list[Decimal] = []

        for elem in root.iter(name_tag):
            disp = elem.find("DSPDISPNAME")
            if disp is not None and disp.text:
                names.append(disp.text.strip())
            else:
                names.append("")

        for elem in root.iter(amt_tag):
            dr = Decimal("0")
            cr = Decimal("0")
            dr_elem = elem.find("DSPCLDRAMT/DSPCLDRAMTA")
            if dr_elem is not None and dr_elem.text and dr_elem.text.strip():
                dr = TallyXMLParser.parse_amount(dr_elem.text.strip())
            cr_elem = elem.find("DSPCLCRAMT/DSPCLCRAMTA")
            if cr_elem is not None and cr_elem.text and cr_elem.text.strip():
                cr = TallyXMLParser.parse_amount(cr_elem.text.strip())
            debits.append(dr)
            credits.append(cr)

        count = min(len(names), len(debits), len(credits))
        result: list[ReportLine] = []
        for i in range(count):
            if names[i]:
                result.append(
                    ReportLine(
                        name=names[i],
                        closing_debit=debits[i],
                        closing_credit=credits[i],
                    )
                )
        return result

    @staticmethod
    def _parse_trial_balance_report(
        root: ET.Element,
    ) -> list[TrialBalanceLine]:
        """Parse Trial Balance report (DSPACCNAME/DSPACCINFO pattern).

        The Tally Trial Balance report returns paired groups of
        ``<DSPACCNAME>`` and ``<DSPACCINFO>`` elements at the ENVELOPE
        level.
        """
        names: list[str] = []
        dr_amounts: list[Decimal] = []
        cr_amounts: list[Decimal] = []

        for elem in root.iter("DSPACCNAME"):
            disp = elem.find("DSPDISPNAME")
            if disp is not None and disp.text:
                names.append(disp.text.strip())
            else:
                names.append("")

        for elem in root.iter("DSPACCINFO"):
            dr = Decimal("0")
            cr = Decimal("0")
            dr_elem = elem.find("DSPCLDRAMT/DSPCLDRAMTA")
            if dr_elem is not None and dr_elem.text and dr_elem.text.strip():
                dr = TallyXMLParser.parse_amount(dr_elem.text.strip())
            cr_elem = elem.find("DSPCLCRAMT/DSPCLCRAMTA")
            if cr_elem is not None and cr_elem.text and cr_elem.text.strip():
                cr = TallyXMLParser.parse_amount(cr_elem.text.strip())
            dr_amounts.append(dr)
            cr_amounts.append(cr)

        count = min(len(names), len(dr_amounts), len(cr_amounts))
        result: list[TrialBalanceLine] = []
        for i in range(count):
            if names[i]:
                result.append(
                    TrialBalanceLine(
                        ledger=names[i],
                        group="",
                        closing_debit=dr_amounts[i],
                        closing_credit=cr_amounts[i],
                    )
                )
        return result

    @staticmethod
    def _parse_day_book_report(
        root: ET.Element,
    ) -> list[dict[str, object]]:
        """Parse Day Book report into simplified voucher dicts.

        The Day Book response contains ``<TALLYMESSAGE>`` with
        ``<VOUCHER>`` elements, similar to collection exports.
        """
        vouchers: list[dict[str, object]] = []
        for v_elem in root.iter("VOUCHER"):
            v: dict[str, object] = {}
            date_elem = v_elem.find("DATE")
            if date_elem is not None and date_elem.text:
                parsed = TallyXMLParser.parse_date(date_elem.text.strip())
                if parsed is not None:
                    v["date"] = parsed
            type_elem = v_elem.find("VOUCHERTYPENAME")
            if type_elem is not None and type_elem.text:
                v["voucher_type"] = type_elem.text.strip()
            num_elem = v_elem.find("VOUCHERNUMBER")
            if num_elem is not None and num_elem.text:
                v["voucher_number"] = num_elem.text.strip()
            narr_elem = v_elem.find("NARRATION")
            if narr_elem is not None and narr_elem.text:
                v["narration"] = narr_elem.text.strip()
            guid_elem = v_elem.find("GUID")
            if guid_elem is not None and guid_elem.text:
                v["guid"] = guid_elem.text.strip()
            if v:
                vouchers.append(v)
        return vouchers

    @staticmethod
    def parse_gstr3b(xml_str: str) -> list["GSTR3BSection"]:
        """Parse a GSTR-3B XML report response into structured sections.

        TallyPrime returns GSTR-3B data using DSPDISPNAME/DSPACCINFO
        groups similar to other reports. We extract section names and
        tax amounts (IGST, CGST, SGST, Cess).
        """
        from tallybridge.models.report import GSTR3BSection

        sections: list[GSTR3BSection] = []
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return sections

        current_section = ""
        for elem in root.iter():
            tag = elem.tag.upper()
            if tag == "DSPDISPNAME" and elem.text:
                name = elem.text.strip()
                if name and not name.startswith("-"):
                    current_section = name
            elif tag == "DSPACCINFO" and current_section:
                taxable = Decimal("0")
                igst = Decimal("0")
                cgst = Decimal("0")
                sgst = Decimal("0")
                cess = Decimal("0")
                for sub in elem.iter():
                    stag = sub.tag.upper()
                    if "TAXABLE" in stag and sub.text:
                        taxable = TallyXMLParser.parse_amount(sub.text)
                    elif "IGST" in stag and sub.text:
                        igst = TallyXMLParser.parse_amount(sub.text)
                    elif "CGST" in stag and sub.text:
                        cgst = TallyXMLParser.parse_amount(sub.text)
                    elif "SGST" in stag or "SCTAX" in stag:
                        if sub.text:
                            sgst = TallyXMLParser.parse_amount(sub.text)
                    elif "CESS" in stag and sub.text:
                        cess = TallyXMLParser.parse_amount(sub.text)
                if taxable or igst or cgst or sgst or cess:
                    sections.append(
                        GSTR3BSection(
                            section=current_section,
                            description=current_section,
                            taxable_value=taxable,
                            integrated_tax=igst,
                            central_tax=cgst,
                            state_tax=sgst,
                            cess=cess,
                        )
                    )
                    current_section = ""
        return sections

    @staticmethod
    def parse_gstr1(xml_str: str) -> list["GSTR1Section"]:
        """Parse a GSTR-1 TYPE=Data XML response into structured sections.

        The XML structure uses DSPACCNAME/DSPACCINFO patterns similar to
        other Tally reports. Each section corresponds to a GSTR-1 table
        (B2B, B2CL, B2CS, CDNR, CDNUR, HSN, DOC_ISSUE).
        """
        from tallybridge.models.report import GSTR1Invoice, GSTR1Section

        sections: list[GSTR1Section] = []
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return sections

        current_section_name = ""
        current_invoices: list[GSTR1Invoice] = []
        section_taxable = Decimal("0")
        section_cgst = Decimal("0")
        section_sgst = Decimal("0")
        section_igst = Decimal("0")
        section_cess = Decimal("0")

        def _flush_section() -> None:
            nonlocal current_section_name, current_invoices
            nonlocal section_taxable, section_cgst
            nonlocal section_sgst, section_igst, section_cess
            if not current_section_name:
                return
            sections.append(
                GSTR1Section(
                    section=current_section_name,
                    description=current_section_name,
                    invoices=list(current_invoices),
                    taxable_value=section_taxable,
                    cgst=section_cgst,
                    sgst=section_sgst,
                    igst=section_igst,
                    cess=section_cess,
                )
            )
            current_section_name = ""
            current_invoices = []
            section_taxable = Decimal("0")
            section_cgst = Decimal("0")
            section_sgst = Decimal("0")
            section_igst = Decimal("0")
            section_cess = Decimal("0")

        for elem in root.iter():
            tag = elem.tag.upper()
            if tag == "DSPDISPNAME" and elem.text:
                name = elem.text.strip()
                if name and not name.startswith("-"):
                    _flush_section()
                    current_section_name = name
            elif tag == "DSPACCINFO" and current_section_name:
                taxable = Decimal("0")
                igst = Decimal("0")
                cgst = Decimal("0")
                sgst = Decimal("0")
                cess = Decimal("0")
                inv_number = ""
                inv_date: date | None = None
                party_gstin = ""
                party_name = ""
                place_of_supply = ""
                supply_type = ""
                for sub in elem.iter():
                    stag = sub.tag.upper()
                    if "TAXABLE" in stag and sub.text:
                        taxable = TallyXMLParser.parse_amount(sub.text)
                    elif "IGST" in stag and sub.text:
                        igst = TallyXMLParser.parse_amount(sub.text)
                    elif "CGST" in stag and sub.text:
                        cgst = TallyXMLParser.parse_amount(sub.text)
                    elif ("SGST" in stag or "SCTAX" in stag) and sub.text:
                        sgst = TallyXMLParser.parse_amount(sub.text)
                    elif "CESS" in stag and sub.text:
                        cess = TallyXMLParser.parse_amount(sub.text)
                    elif stag == "VOUCHERNUMBER" and sub.text:
                        inv_number = sub.text.strip()
                    elif stag == "DATE" and sub.text:
                        inv_date = TallyXMLParser.parse_date(sub.text.strip())
                    elif stag == "PARTYGSTIN" and sub.text:
                        party_gstin = sub.text.strip()
                    elif stag in ("PARTYNAME", "PARTYLEDGERNAME") and sub.text:
                        party_name = sub.text.strip()
                    elif stag == "PLACEOFSUPPLY" and sub.text:
                        place_of_supply = sub.text.strip()
                    elif stag == "SUPPLYTYPE" and sub.text:
                        supply_type = sub.text.strip()

                if taxable or igst or cgst or sgst or cess:
                    current_invoices.append(
                        GSTR1Invoice(
                            invoice_number=inv_number,
                            invoice_date=inv_date,
                            party_gstin=party_gstin,
                            party_name=party_name,
                            place_of_supply=place_of_supply,
                            taxable_value=taxable,
                            cgst=cgst,
                            sgst=sgst,
                            igst=igst,
                            cess=cess,
                            supply_type=supply_type,
                        )
                    )
                    section_taxable += taxable
                    section_cgst += cgst
                    section_sgst += sgst
                    section_igst += igst
                    section_cess += cess

        _flush_section()
        return sections


class TallyJSONParser:
    """Parse TallyPrime 7.0+ JSONEx responses into the same Pydantic models.

    Reuses static helpers from TallyXMLParser (parse_amount, parse_date,
    parse_bool, parse_quantity, parse_rate) since JSONEx amounts still use
    "1234.56 Dr" format and dates are still YYYYMMDD strings.

    JSONEx key names are lowercase (e.g. "name" not "NAME",
    "ledgerentries.list" not "ALLLEDGERENTRIES.LIST").
    """

    @staticmethod
    def _get_val(obj: dict[str, Any] | None, key: str, default: str = "") -> str:
        if obj is None:
            return default
        val = obj.get(key)
        if val is None:
            return default
        if isinstance(val, str):
            return val
        return str(val)

    @staticmethod
    def _get_list(obj: dict[str, Any], key: str) -> list[dict[str, Any]]:
        val = obj.get(key)
        if val is None:
            return []
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            return [val]
        return []

    def parse_ledgers_json(self, data: dict[str, Any]) -> list[TallyLedger]:
        messages = self._get_tally_messages(data)
        ledgers: list[TallyLedger] = []
        for msg in messages:
            ledger_data = msg.get("ledger")
            if ledger_data is None:
                continue
            try:
                ledger = TallyLedger(
                    name=self._get_val(ledger_data, "name"),
                    guid=self._get_val(ledger_data, "guid"),
                    alter_id=int(self._get_val(ledger_data, "alterid", "0")),
                    parent_group=self._get_val(ledger_data, "parent"),
                    opening_balance=TallyXMLParser.parse_amount(
                        self._get_val(ledger_data, "openingbalance")
                    ),
                    closing_balance=TallyXMLParser.parse_amount(
                        self._get_val(ledger_data, "closingbalance")
                    ),
                    is_revenue=TallyXMLParser.parse_bool(
                        self._get_val(ledger_data, "isrevenue")
                    ),
                    affects_gross_profit=TallyXMLParser.parse_bool(
                        self._get_val(ledger_data, "affectsgrossprofit")
                    ),
                    gstin=self._get_val(ledger_data, "gstin") or None,
                    party_name=self._get_val(ledger_data, "ledmailingname") or None,
                )
                ledgers.append(ledger)
            except Exception as exc:
                logger.warning("Failed to parse ledger JSON: {}", exc)
        return ledgers

    def parse_groups_json(self, data: dict[str, Any]) -> list[TallyGroup]:
        messages = self._get_tally_messages(data)
        groups: list[TallyGroup] = []
        for msg in messages:
            group_data = msg.get("group")
            if group_data is None:
                continue
            try:
                group = TallyGroup(
                    name=self._get_val(group_data, "name"),
                    guid=self._get_val(group_data, "guid"),
                    alter_id=int(self._get_val(group_data, "alterid", "0")),
                    parent=self._get_val(group_data, "parent"),
                    primary_group=self._get_val(group_data, "primarygroup"),
                    is_revenue=TallyXMLParser.parse_bool(
                        self._get_val(group_data, "isrevenue")
                    ),
                    affects_gross_profit=TallyXMLParser.parse_bool(
                        self._get_val(group_data, "affectsgrossprofit")
                    ),
                    net_debit_credit=self._get_val(group_data, "netdebitcredit", "Dr"),
                )
                groups.append(group)
            except Exception as exc:
                logger.warning("Failed to parse group JSON: {}", exc)
        return groups

    def parse_stock_items_json(self, data: dict[str, Any]) -> list[TallyStockItem]:
        messages = self._get_tally_messages(data)
        items: list[TallyStockItem] = []
        for msg in messages:
            item_data = msg.get("stockitem")
            if item_data is None:
                continue
            try:
                closing_balance_text = self._get_val(item_data, "closingbalance")
                closing_qty = TallyXMLParser.parse_quantity(closing_balance_text)
                stock_item = TallyStockItem(
                    name=self._get_val(item_data, "name"),
                    guid=self._get_val(item_data, "guid"),
                    alter_id=int(self._get_val(item_data, "alterid", "0")),
                    parent_group=self._get_val(item_data, "parent"),
                    unit=self._get_val(item_data, "baseunits"),
                    gst_rate=TallyXMLParser.parse_amount(
                        self._get_val(item_data, "gstrate")
                    )
                    or None,
                    hsn_code=self._get_val(item_data, "hsncode") or None,
                    closing_quantity=closing_qty,
                    closing_value=TallyXMLParser.parse_amount(
                        self._get_val(item_data, "closingvalue")
                    ),
                )
                items.append(stock_item)
            except Exception as exc:
                logger.warning("Failed to parse stock item JSON: {}", exc)
        return items

    def parse_stock_groups_json(self, data: dict[str, Any]) -> list[TallyStockGroup]:
        messages = self._get_tally_messages(data)
        groups: list[TallyStockGroup] = []
        for msg in messages:
            sg_data = msg.get("stockgroup")
            if sg_data is None:
                continue
            try:
                sg = TallyStockGroup(
                    name=self._get_val(sg_data, "name"),
                    guid=self._get_val(sg_data, "guid"),
                    alter_id=int(self._get_val(sg_data, "alterid", "0")),
                    parent=self._get_val(sg_data, "parent"),
                    should_quantities_add=TallyXMLParser.parse_bool(
                        self._get_val(sg_data, "shouldquantitiesadd")
                    ),
                )
                groups.append(sg)
            except Exception as exc:
                logger.warning("Failed to parse stock group JSON: {}", exc)
        return groups

    def parse_units_json(self, data: dict[str, Any]) -> list[TallyUnit]:
        messages = self._get_tally_messages(data)
        units: list[TallyUnit] = []
        for msg in messages:
            unit_data = msg.get("unit")
            if unit_data is None:
                continue
            try:
                unit = TallyUnit(
                    name=self._get_val(unit_data, "name"),
                    guid=self._get_val(unit_data, "guid"),
                    alter_id=int(self._get_val(unit_data, "alterid", "0")),
                    unit_type=self._get_val(unit_data, "unittype", "Simple"),
                    base_units=self._get_val(unit_data, "baseunits") or None,
                    decimal_places=int(self._get_val(unit_data, "decimalplaces", "0")),
                    symbol=self._get_val(unit_data, "symbol") or None,
                )
                units.append(unit)
            except Exception as exc:
                logger.warning("Failed to parse unit JSON: {}", exc)
        return units

    def parse_voucher_types_json(self, data: dict[str, Any]) -> list[TallyVoucherType]:
        messages = self._get_tally_messages(data)
        vtypes: list[TallyVoucherType] = []
        for msg in messages:
            vt_data = msg.get("vouchertype")
            if vt_data is None:
                continue
            try:
                vtype = TallyVoucherType(
                    name=self._get_val(vt_data, "name"),
                    guid=self._get_val(vt_data, "guid"),
                    alter_id=int(self._get_val(vt_data, "alterid", "0")),
                    parent=self._get_val(vt_data, "parent"),
                )
                vtypes.append(vtype)
            except Exception as exc:
                logger.warning("Failed to parse voucher type JSON: {}", exc)
        return vtypes

    def parse_cost_centers_json(self, data: dict[str, Any]) -> list[TallyCostCenter]:
        messages = self._get_tally_messages(data)
        centers: list[TallyCostCenter] = []
        for msg in messages:
            cc_data = msg.get("costcentre")
            if cc_data is None:
                continue
            try:
                cc = TallyCostCenter(
                    name=self._get_val(cc_data, "name"),
                    guid=self._get_val(cc_data, "guid"),
                    alter_id=int(self._get_val(cc_data, "alterid", "0")),
                    parent=self._get_val(cc_data, "parent"),
                    email=self._get_val(cc_data, "email") or None,
                    cost_centre_type=self._get_val(
                        cc_data, "costcentretype", "Primary"
                    ),
                )
                centers.append(cc)
            except Exception as exc:
                logger.warning("Failed to parse cost centre JSON: {}", exc)
        return centers

    def parse_godowns_json(self, data: dict[str, Any]) -> list[TallyGodown]:
        messages = self._get_tally_messages(data)
        godowns: list[TallyGodown] = []
        for msg in messages:
            godown_data = msg.get("godown")
            if godown_data is None:
                continue
            try:
                godown = TallyGodown(
                    name=self._get_val(godown_data, "name"),
                    guid=self._get_val(godown_data, "guid"),
                    alter_id=int(self._get_val(godown_data, "alterid", "0")),
                    parent=self._get_val(godown_data, "parent") or None,
                )
                godowns.append(godown)
            except Exception as exc:
                logger.warning("Failed to parse godown JSON: {}", exc)
        return godowns

    def parse_vouchers_json(self, data: dict[str, Any]) -> list[TallyVoucher]:
        messages = self._get_tally_messages(data)
        vouchers: list[TallyVoucher] = []
        for msg in messages:
            v_data = msg.get("voucher")
            if v_data is None:
                continue
            try:
                ledger_entries = self._parse_ledger_entries_json(v_data)
                inventory_entries = self._parse_inventory_entries_json(v_data)
                cost_centre_allocations = self._parse_cost_centre_allocations_json(
                    v_data
                )
                bill_allocations = self._parse_bill_allocations_json(v_data)
                total_amount = sum(
                    (e.amount for e in ledger_entries if e.amount > 0),
                    Decimal("0"),
                )
                gst_amount = sum(
                    (
                        e.amount
                        for e in ledger_entries
                        if "GST" in e.ledger_name.upper()
                    ),
                    Decimal("0"),
                )
                parsed_date = TallyXMLParser.parse_date(self._get_val(v_data, "date"))
                if parsed_date is None:
                    logger.warning(
                        "Skipping voucher with unparseable date: guid={}",
                        self._get_val(v_data, "guid"),
                    )
                    continue
                voucher = TallyVoucher(
                    guid=self._get_val(v_data, "guid"),
                    alter_id=int(self._get_val(v_data, "alterid", "0")),
                    voucher_number=self._get_val(v_data, "vouchernumber"),
                    voucher_type=self._get_val(v_data, "vouchertypename"),
                    date=parsed_date,
                    effective_date=TallyXMLParser.parse_date(
                        self._get_val(v_data, "effectivedate")
                    ),
                    reference=self._get_val(v_data, "reference") or None,
                    narration=self._get_val(v_data, "narration") or None,
                    is_cancelled=TallyXMLParser.parse_bool(
                        self._get_val(v_data, "iscancelled")
                    ),
                    is_optional=TallyXMLParser.parse_bool(
                        self._get_val(v_data, "isoptional")
                    ),
                    is_postdated=TallyXMLParser.parse_bool(
                        self._get_val(v_data, "ispostdated")
                    ),
                    is_void=TallyXMLParser.parse_bool(self._get_val(v_data, "isvoid")),
                    party_ledger=self._get_val(v_data, "partyledgername") or None,
                    party_gstin=self._get_val(v_data, "partygstin") or None,
                    place_of_supply=self._get_val(v_data, "placeofsupply") or None,
                    due_date=TallyXMLParser.parse_date(
                        self._get_val(v_data, "basicduedateofpymt")
                    ),
                    entered_by=self._get_val(v_data, "enteredby") or None,
                    ledger_entries=ledger_entries,
                    inventory_entries=inventory_entries,
                    cost_centre_allocations=cost_centre_allocations,
                    bill_allocations=bill_allocations,
                    total_amount=abs(total_amount),
                    gst_amount=abs(gst_amount),
                )
                vouchers.append(voucher)
            except Exception as exc:
                logger.warning("Failed to parse voucher JSON: {}", exc)
        return vouchers

    def _parse_ledger_entries_json(
        self, v_data: dict[str, Any]
    ) -> list[TallyVoucherEntry]:
        entries: list[TallyVoucherEntry] = []
        all_key = "allledgerentries.list"
        reg_key = "ledgerentries.list"
        raw_entries = self._get_list(v_data, all_key)
        if not raw_entries:
            raw_entries = self._get_list(v_data, reg_key)
        for entry in raw_entries:
            name = self._get_val(entry, "ledgername")
            amount = TallyXMLParser.parse_amount(self._get_val(entry, "amount"))
            entries.append(TallyVoucherEntry(ledger_name=name, amount=amount))
        return entries

    def _parse_inventory_entries_json(
        self, v_data: dict[str, Any]
    ) -> list[TallyInventoryEntry]:
        entries: list[TallyInventoryEntry] = []
        all_key = "allinventoryentries.list"
        reg_key = "inventoryentries.list"
        raw_entries = self._get_list(v_data, all_key)
        if not raw_entries:
            raw_entries = self._get_list(v_data, reg_key)
        for entry in raw_entries:
            name = self._get_val(entry, "stockitemname")
            qty = TallyXMLParser.parse_quantity(self._get_val(entry, "actualqty"))
            rate = TallyXMLParser.parse_rate(self._get_val(entry, "rate"))
            amount = TallyXMLParser.parse_amount(self._get_val(entry, "amount"))
            godown = self._get_val(entry, "godown") or None
            batch = self._get_val(entry, "batch") or None
            entries.append(
                TallyInventoryEntry(
                    stock_item_name=name,
                    quantity=qty,
                    rate=rate,
                    amount=amount,
                    godown=godown,
                    batch=batch,
                )
            )
        return entries

    def _parse_cost_centre_allocations_json(
        self, v_data: dict[str, Any]
    ) -> list[TallyCostCentreAllocation]:
        allocations: list[TallyCostCentreAllocation] = []
        all_key = "allledgerentries.list"
        reg_key = "ledgerentries.list"
        raw_entries = self._get_list(v_data, all_key)
        if not raw_entries:
            raw_entries = self._get_list(v_data, reg_key)
        for entry in raw_entries:
            ledger_name = self._get_val(entry, "ledgername")
            for cc in self._get_list(entry, "costcentre.list"):
                cc_name = self._get_val(cc, "costcentrename")
                amount = TallyXMLParser.parse_amount(self._get_val(cc, "amount"))
                allocations.append(
                    TallyCostCentreAllocation(
                        ledger_name=ledger_name,
                        cost_centre=cc_name,
                        amount=amount,
                    )
                )
            for cat in self._get_list(entry, "categoryallocations.list"):
                for cc in self._get_list(cat, "costcentre.list"):
                    cc_name = self._get_val(cc, "costcentrename")
                    amount = TallyXMLParser.parse_amount(self._get_val(cc, "amount"))
                    allocations.append(
                        TallyCostCentreAllocation(
                            ledger_name=ledger_name,
                            cost_centre=cc_name,
                            amount=amount,
                        )
                    )
        return allocations

    def _parse_bill_allocations_json(
        self, v_data: dict[str, Any]
    ) -> list[TallyBillAllocation]:
        allocations: list[TallyBillAllocation] = []
        all_key = "allledgerentries.list"
        reg_key = "ledgerentries.list"
        raw_entries = self._get_list(v_data, all_key)
        if not raw_entries:
            raw_entries = self._get_list(v_data, reg_key)
        for entry in raw_entries:
            ledger_name = self._get_val(entry, "ledgername")
            for bill in self._get_list(entry, "billallocations.list"):
                bill_type = self._get_val(bill, "billtype") or None
                bill_name = self._get_val(bill, "name")
                amount = TallyXMLParser.parse_amount(self._get_val(bill, "amount"))
                bcp_data = bill.get("billcreditperiod")
                bill_credit_period = self._parse_bill_credit_period_json(bcp_data)
                allocations.append(
                    TallyBillAllocation(
                        ledger_name=ledger_name,
                        bill_name=bill_name,
                        amount=amount,
                        bill_type=bill_type,
                        bill_credit_period=bill_credit_period,
                    )
                )
        return allocations

    @staticmethod
    def _parse_bill_credit_period_json(
        bcp_data: Any,
    ) -> int | None:
        if bcp_data is None:
            return None
        if isinstance(bcp_data, (int, float)):
            return int(bcp_data)
        if isinstance(bcp_data, str):
            try:
                return int(bcp_data.strip())
            except ValueError:
                pass
            return None
        if isinstance(bcp_data, dict):
            in_days = bcp_data.get("indays")
            if in_days is not None:
                try:
                    return int(in_days)
                except (ValueError, TypeError):
                    pass
        return None

    @staticmethod
    def _get_tally_messages(data: dict[str, Any]) -> list[dict[str, Any]]:
        inner = data.get("data", data)
        messages = inner.get("tallymessage", [])
        if isinstance(messages, dict):
            return [messages]
        if isinstance(messages, list):
            return messages
        return []

    @staticmethod
    def parse_report_json(
        data: dict[str, Any],
        report_name: str = "Unknown",
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> TallyReport:
        from tallybridge.models.report import TallyReportType

        report_type: TallyReportType = "Unknown"
        if "balance sheet" in report_name.lower():
            report_type = "Balance Sheet"
        elif "profit" in report_name.lower():
            report_type = "Profit & Loss"
        elif "trial balance" in report_name.lower():
            report_type = "Trial Balance"
        elif "day book" in report_name.lower():
            report_type = "Day Book"

        inner = data.get("data", data)

        if report_type == "Trial Balance":
            tb_lines = TallyJSONParser._parse_trial_balance_json(inner)
            return TallyReport(
                report_type=report_type,
                from_date=from_date,
                to_date=to_date,
                trial_balance=tb_lines,
            )

        if report_type == "Day Book":
            vouchers = TallyJSONParser._parse_day_book_json(inner)
            return TallyReport(
                report_type=report_type,
                from_date=from_date,
                to_date=to_date,
                vouchers=vouchers,
            )

        if report_type in ("Balance Sheet", "Profit & Loss"):
            lines = TallyJSONParser._parse_bs_pl_json(inner)
            return TallyReport(
                report_type=report_type,
                from_date=from_date,
                to_date=to_date,
                lines=lines,
            )

        return TallyReport(
            report_type=report_type,
            from_date=from_date,
            to_date=to_date,
        )

    @staticmethod
    def _parse_bs_pl_json(data: dict[str, Any]) -> list[ReportLine]:
        result: list[ReportLine] = []
        dsp_acc_name_list = data.get("dspaccname", [])
        dsp_acc_info_list = data.get("dspaccinfo", [])

        if isinstance(dsp_acc_name_list, dict):
            dsp_acc_name_list = [dsp_acc_name_list]
        if isinstance(dsp_acc_info_list, dict):
            dsp_acc_info_list = [dsp_acc_info_list]

        count = min(len(dsp_acc_name_list), len(dsp_acc_info_list))
        for i in range(count):
            name_item = dsp_acc_name_list[i]
            info_item = dsp_acc_info_list[i]
            if isinstance(name_item, dict):
                name = name_item.get("dspdispname", "")
            else:
                name = str(name_item)
            if not name:
                continue
            dr = Decimal("0")
            cr = Decimal("0")
            if isinstance(info_item, dict):
                dr_val = info_item.get("dspcldramt", {})
                cr_val = info_item.get("dspclcramt", {})
                if isinstance(dr_val, dict):
                    dr = TallyXMLParser.parse_amount(
                        str(dr_val.get("dspcldramta", "0"))
                    )
                if isinstance(cr_val, dict):
                    cr = TallyXMLParser.parse_amount(
                        str(cr_val.get("dspclcramta", "0"))
                    )
            result.append(
                ReportLine(
                    name=name,
                    closing_debit=dr,
                    closing_credit=cr,
                )
            )
        return result

    @staticmethod
    def _parse_trial_balance_json(data: dict[str, Any]) -> list[TrialBalanceLine]:
        result: list[TrialBalanceLine] = []
        dsp_acc_name_list = data.get("dspaccname", [])
        dsp_acc_info_list = data.get("dspaccinfo", [])

        if isinstance(dsp_acc_name_list, dict):
            dsp_acc_name_list = [dsp_acc_name_list]
        if isinstance(dsp_acc_info_list, dict):
            dsp_acc_info_list = [dsp_acc_info_list]

        count = min(len(dsp_acc_name_list), len(dsp_acc_info_list))
        for i in range(count):
            name_item = dsp_acc_name_list[i]
            info_item = dsp_acc_info_list[i]
            if isinstance(name_item, dict):
                name = name_item.get("dspdispname", "")
            else:
                name = str(name_item)
            if not name:
                continue
            dr = Decimal("0")
            cr = Decimal("0")
            if isinstance(info_item, dict):
                dr_val = info_item.get("dspcldramt", {})
                cr_val = info_item.get("dspclcramt", {})
                if isinstance(dr_val, dict):
                    dr = TallyXMLParser.parse_amount(
                        str(dr_val.get("dspcldramta", "0"))
                    )
                if isinstance(cr_val, dict):
                    cr = TallyXMLParser.parse_amount(
                        str(cr_val.get("dspclcramta", "0"))
                    )
            result.append(
                TrialBalanceLine(
                    ledger=name,
                    group="",
                    closing_debit=dr,
                    closing_credit=cr,
                )
            )
        return result

    @staticmethod
    def _parse_day_book_json(
        data: dict[str, Any],
    ) -> list[dict[str, object]]:
        messages = TallyJSONParser._get_tally_messages({"data": data})
        vouchers: list[dict[str, object]] = []
        for msg in messages:
            v_data = msg.get("voucher")
            if v_data is None:
                continue
            v: dict[str, object] = {}
            parsed = TallyXMLParser.parse_date(TallyJSONParser._get_val(v_data, "date"))
            if parsed is not None:
                v["date"] = parsed
            vt = TallyJSONParser._get_val(v_data, "vouchertypename")
            if vt:
                v["voucher_type"] = vt
            vn = TallyJSONParser._get_val(v_data, "vouchernumber")
            if vn:
                v["voucher_number"] = vn
            narr = TallyJSONParser._get_val(v_data, "narration")
            if narr:
                v["narration"] = narr
            guid = TallyJSONParser._get_val(v_data, "guid")
            if guid:
                v["guid"] = guid
            if v:
                vouchers.append(v)
        return vouchers

    @staticmethod
    def parse_gstr3b_json(data: dict[str, Any]) -> list["GSTR3BSection"]:
        """Parse a GSTR-3B JSON response into structured sections."""
        from tallybridge.models.report import GSTR3BSection

        sections: list[GSTR3BSection] = []
        messages = TallyJSONParser._get_tally_messages(data)
        for msg in messages:
            for _key, obj in msg.items():
                if not isinstance(obj, dict):
                    continue
                section_name = (
                    TallyJSONParser._get_val(obj, "dspdispname")
                    or TallyJSONParser._get_val(obj, "name")
                    or ""
                )
                if not section_name:
                    continue
                taxable = TallyXMLParser.parse_amount(
                    TallyJSONParser._get_val(obj, "taxablevalue", "0")
                )
                igst = TallyXMLParser.parse_amount(
                    TallyJSONParser._get_val(obj, "integratedtax", "0")
                )
                cgst = TallyXMLParser.parse_amount(
                    TallyJSONParser._get_val(obj, "centraltax", "0")
                )
                sgst = TallyXMLParser.parse_amount(
                    TallyJSONParser._get_val(obj, "statetax", "0")
                )
                cess = TallyXMLParser.parse_amount(
                    TallyJSONParser._get_val(obj, "cess", "0")
                )
                if taxable or igst or cgst or sgst or cess:
                    sections.append(
                        GSTR3BSection(
                            section=section_name,
                            description=section_name,
                            taxable_value=taxable,
                            integrated_tax=igst,
                            central_tax=cgst,
                            state_tax=sgst,
                            cess=cess,
                        )
                    )
        return sections

    @staticmethod
    def parse_gstr1_json(data: dict[str, Any]) -> list["GSTR1Section"]:
        """Parse a GSTR-1 JSON response into structured sections."""
        from tallybridge.models.report import GSTR1Invoice, GSTR1Section

        sections: list[GSTR1Section] = []
        messages = TallyJSONParser._get_tally_messages(data)
        for msg in messages:
            for _key, obj in msg.items():
                if not isinstance(obj, dict):
                    continue
                section_name = (
                    TallyJSONParser._get_val(obj, "dspdispname")
                    or TallyJSONParser._get_val(obj, "name")
                    or ""
                )
                if not section_name:
                    continue
                invoices: list[GSTR1Invoice] = []
                taxable = TallyXMLParser.parse_amount(
                    TallyJSONParser._get_val(obj, "taxablevalue", "0")
                )
                igst = TallyXMLParser.parse_amount(
                    TallyJSONParser._get_val(obj, "integratedtax", "0")
                )
                cgst = TallyXMLParser.parse_amount(
                    TallyJSONParser._get_val(obj, "centraltax", "0")
                )
                sgst = TallyXMLParser.parse_amount(
                    TallyJSONParser._get_val(obj, "statetax", "0")
                )
                cess = TallyXMLParser.parse_amount(
                    TallyJSONParser._get_val(obj, "cess", "0")
                )
                inv_number = TallyJSONParser._get_val(obj, "vouchernumber", "")
                inv_date_str = TallyJSONParser._get_val(obj, "date", "")
                inv_date = TallyXMLParser.parse_date(inv_date_str)
                party_gstin = TallyJSONParser._get_val(obj, "partygstin", "")
                party_name = TallyJSONParser._get_val(obj, "partyname", "")
                place_of_supply = TallyJSONParser._get_val(obj, "placeofsupply", "")
                supply_type = TallyJSONParser._get_val(obj, "supplytype", "")
                if taxable or igst or cgst or sgst or cess:
                    invoices.append(
                        GSTR1Invoice(
                            invoice_number=inv_number,
                            invoice_date=inv_date,
                            party_gstin=party_gstin,
                            party_name=party_name,
                            place_of_supply=place_of_supply,
                            taxable_value=taxable,
                            cgst=cgst,
                            sgst=sgst,
                            igst=igst,
                            cess=cess,
                            supply_type=supply_type,
                        )
                    )
                sections.append(
                    GSTR1Section(
                        section=section_name,
                        description=section_name,
                        invoices=invoices,
                        taxable_value=taxable,
                        cgst=cgst,
                        sgst=sgst,
                        igst=igst,
                        cess=cess,
                    )
                )
        return sections
