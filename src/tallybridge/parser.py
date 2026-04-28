"""Tally XML parser — see SPECS.md §5."""

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation

from loguru import logger

from tallybridge.models.master import (
    TallyCostCenter,
    TallyGroup,
    TallyLedger,
    TallyStockGroup,
    TallyStockItem,
    TallyUnit,
    TallyVoucherType,
)
from tallybridge.models.report import OutstandingBill
from tallybridge.models.voucher import (
    TallyBillAllocation,
    TallyCostCentreAllocation,
    TallyInventoryEntry,
    TallyVoucher,
    TallyVoucherEntry,
)


class TallyXMLParser:
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
