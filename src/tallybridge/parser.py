"""Tally XML parser — see SPECS.md §5."""

import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

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
from tallybridge.models.voucher import TallyInventoryEntry, TallyVoucher, TallyVoucherEntry


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
        """Safely get text from a child tag. Returns default if missing or empty."""
        if element is None:
            return default
        child = element.find(tag)
        if child is None or child.text is None:
            return default
        return child.text

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
                    opening_balance=self.parse_amount(self.get_text(elem, "OPENINGBALANCE")),
                    closing_balance=self.parse_amount(self.get_text(elem, "CLOSINGBALANCE")),
                    is_revenue=self.parse_bool(self.get_text(elem, "ISREVENUE")),
                    affects_gross_profit=self.parse_bool(self.get_text(elem, "AFFECTSGROSSPROFIT")),
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
                    affects_gross_profit=self.parse_bool(self.get_text(elem, "AFFECTSGROSSPROFIT")),
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
                    closing_value=self.parse_amount(self.get_text(elem, "CLOSINGVALUE")),
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
                    should_quantities_add=self.parse_bool(self.get_text(elem, "SHOULDQUANTITIESADD")),
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
        - <INVENTORYENTRIES.LIST> sub-elements with STOCKITEMNAME, ACTUALQTY, RATE, AMOUNT
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
                total_amount = sum(
                    (e.amount for e in ledger_entries if e.amount > 0),
                    Decimal("0"),
                )
                gst_amount = sum(
                    (e.amount for e in ledger_entries if "GST" in e.ledger_name.upper()),
                    Decimal("0"),
                )
                voucher = TallyVoucher(
                    guid=self.get_text(elem, "GUID"),
                    alter_id=int(self.get_text(elem, "ALTERID", "0")),
                    voucher_number=self.get_text(elem, "VOUCHERNUMBER"),
                    voucher_type=self.get_text(elem, "VOUCHERTYPENAME"),
                    date=self.parse_date(self.get_text(elem, "DATE")) or date.today(),
                    effective_date=self.parse_date(self.get_text(elem, "EFFECTIVEDATE")),
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
                bill = OutstandingBill(
                    party_name=self.get_text(elem, "PARTYNAME"),
                    bill_date=self.parse_date(self.get_text(elem, "DATE")) or date.today(),
                    bill_number=self.get_text(elem, "BILLNUMBER"),
                    bill_amount=self.parse_amount(self.get_text(elem, "BILLAMOUNT")),
                    outstanding_amount=self.parse_amount(self.get_text(elem, "OUTSTANDINGAMOUNT")),
                    voucher_type=self.get_text(elem, "VOUCHERTYPENAME", "Sales"),
                )
                bills.append(bill)
            except Exception as exc:
                logger.warning("Failed to parse bill element: {}", exc)
        return bills

    def _parse_ledger_entries(self, voucher_elem: ET.Element) -> list[TallyVoucherEntry]:
        entries: list[TallyVoucherEntry] = []
        for entry in voucher_elem.findall("LEDGERENTRIES.LIST"):
            name = self.get_text(entry, "LEDGERNAME")
            amount_text = self.get_text(entry, "AMOUNT")
            amount = self.parse_amount(amount_text)
            entries.append(TallyVoucherEntry(ledger_name=name, amount=amount))
        return entries

    def _parse_inventory_entries(self, voucher_elem: ET.Element) -> list[TallyInventoryEntry]:
        entries: list[TallyInventoryEntry] = []
        for entry in voucher_elem.findall("INVENTORYENTRIES.LIST"):
            name = self.get_text(entry, "STOCKITEMNAME")
            qty_text = self.get_text(entry, "ACTUALQTY")
            qty = self.parse_quantity(qty_text)
            rate = self.parse_rate(self.get_text(entry, "RATE"))
            amount = self.parse_amount(self.get_text(entry, "AMOUNT"))
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
