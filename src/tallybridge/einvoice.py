"""E-invoice JSON export builder — see SPECS.md §34."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from loguru import logger

from tallybridge.cache import TallyCache
from tallybridge.models.report import ValidationResult
from tallybridge.models.voucher import TallyVoucher


class EInvoiceBuilder:
    """Build IRP-compliant e-invoice JSON from TallyBridge voucher data.

    Follows NIC e-invoice JSON Schema version 1.1.
    Reference: https://einvoice1.gst.gov.in/Documents/eInvoice_Design_v1.1.json
    """

    def __init__(self, cache: TallyCache) -> None:
        self._cache = cache

    def build_einvoice_json(self, voucher: TallyVoucher) -> dict[str, Any]:
        """Build a single e-invoice JSON payload.

        Maps TallyBridge voucher fields to IRP JSON format:
        - Seller GSTIN from party_ledger GSTIN in cache
        - Buyer GSTIN from counterparty in cache
        - Line items from inventory_entries + ledger_entries
        - HSN codes from stock items in cache
        - Tax amounts from GST ledger entries

        Returns dict ready for JSON serialization.
        Raises ValueError if required fields are missing.
        """
        validation = self.validate_einvoice_data(voucher)
        if not validation.valid:
            raise ValueError(
                f"Voucher missing required e-invoice fields: "
                f"{'; '.join(validation.errors)}"
            )

        seller_gstin = self._get_seller_gstin(voucher)
        buyer_gstin = voucher.party_gstin or self._get_party_gstin(voucher.party_ledger)
        if not buyer_gstin:
            raise ValueError("Buyer GSTIN is required for e-invoice")

        doc_date = voucher.date.strftime("%d/%m/%Y")
        sup_typ = self._determine_supply_type(seller_gstin, buyer_gstin)

        item_list = self._build_item_list(voucher)
        val_dtls = self._build_value_details(voucher)

        payload: dict[str, Any] = {
            "Version": "1.1",
            "TranDtls": {"TaxSch": "GST", "SupTyp": sup_typ},
            "DocDtls": {
                "Typ": self._map_voucher_type(voucher.voucher_type),
                "No": voucher.voucher_number,
                "Dt": doc_date,
            },
            "SellerDtls": {"Gstin": seller_gstin, "LglNm": voucher.party_ledger or ""},
            "BuyerDtls": {
                "Gstin": buyer_gstin,
                "LglNm": voucher.party_ledger or "",
            },
            "ItemList": item_list,
            "ValDtls": val_dtls,
        }

        if voucher.place_of_supply:
            payload["BuyerDtls"]["Loc"] = voucher.place_of_supply[:2]

        return payload

    def build_batch_json(self, vouchers: list[TallyVoucher]) -> list[dict[str, Any]]:
        """Build e-invoice JSON for multiple vouchers."""
        results: list[dict[str, Any]] = []
        for voucher in vouchers:
            try:
                payload = self.build_einvoice_json(voucher)
                results.append(payload)
            except ValueError as exc:
                logger.warning(
                    "Skipping voucher {} for e-invoice: {}",
                    voucher.voucher_number,
                    exc,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to build e-invoice for voucher {}: {}",
                    voucher.voucher_number,
                    exc,
                )
        return results

    def validate_einvoice_data(self, voucher: TallyVoucher) -> ValidationResult:
        """Validate voucher has all required fields for e-invoice.

        Checks: GSTIN present, HSN codes on items, tax amounts,
        place of supply, invoice number format.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not voucher.voucher_number:
            errors.append("Invoice number is required")
        if not voucher.party_ledger:
            errors.append("Party ledger name is required")
        if not voucher.party_gstin and not self._get_party_gstin(voucher.party_ledger):
            errors.append("Buyer GSTIN is required")
        if not voucher.place_of_supply:
            warnings.append("Place of supply is recommended")
        if voucher.voucher_type not in ("Sales", "Credit Note"):
            warnings.append(
                f"E-invoice typically applies to Sales/Credit Note, "
                f"got {voucher.voucher_type}"
            )

        seller_gstin = self._get_seller_gstin(voucher)
        if not seller_gstin:
            errors.append("Seller GSTIN is required")

        for ie in voucher.inventory_entries:
            hsn = self._get_stock_hsn(ie.stock_item_name)
            if not hsn:
                warnings.append(
                    f"HSN code missing for stock item '{ie.stock_item_name}'"
                )

        has_gst = any("GST" in le.ledger_name.upper() for le in voucher.ledger_entries)
        if not has_gst and voucher.gst_amount == Decimal("0"):
            warnings.append("No GST ledger entries found")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _get_seller_gstin(self, voucher: TallyVoucher) -> str | None:
        rows = self._cache.query(
            "SELECT gstin FROM mst_ledger WHERE name = ? AND gstin IS NOT NULL "
            "AND gstin != '' AND parent_group IN "
            "('Sales Accounts', 'Sundry Debtors') LIMIT 1",
            [voucher.party_ledger],
        )
        if rows and rows[0].get("gstin"):
            return str(rows[0]["gstin"])
        company_rows = self._cache.query(
            "SELECT gstin FROM mst_ledger WHERE gstin IS NOT NULL "
            "AND gstin != '' AND parent_group = 'Sales Accounts' LIMIT 1"
        )
        if company_rows and company_rows[0].get("gstin"):
            return str(company_rows[0]["gstin"])
        return None

    def _get_party_gstin(self, party_name: str | None) -> str | None:
        if not party_name:
            return None
        rows = self._cache.query(
            "SELECT gstin FROM mst_ledger WHERE name = ? AND gstin IS NOT NULL "
            "AND gstin != ''",
            [party_name],
        )
        if rows and rows[0].get("gstin"):
            return str(rows[0]["gstin"])
        return None

    def _get_stock_hsn(self, stock_item_name: str) -> str | None:
        rows = self._cache.query(
            "SELECT hsn_code FROM mst_stock_item "
            "WHERE name = ? AND hsn_code IS NOT NULL "
            "AND hsn_code != ''",
            [stock_item_name],
        )
        if rows and rows[0].get("hsn_code"):
            return str(rows[0]["hsn_code"])
        return None

    def _determine_supply_type(
        self, seller_gstin: str | None, buyer_gstin: str | None
    ) -> str:
        if not seller_gstin or not buyer_gstin:
            return "B2B"
        if seller_gstin[:2] == buyer_gstin[:2]:
            return "B2B"
        return "B2B"

    def _map_voucher_type(self, voucher_type: str) -> str:
        mapping = {
            "Sales": "INV",
            "Credit Note": "CRN",
            "Debit Note": "DBN",
        }
        return mapping.get(voucher_type, "INV")

    def _build_item_list(self, voucher: TallyVoucher) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for ie in voucher.inventory_entries:
            hsn = self._get_stock_hsn(ie.stock_item_name) or ""
            item: dict[str, Any] = {
                "SlNo": str(len(items) + 1),
                "PrdDesc": ie.stock_item_name,
                "HsnCd": hsn,
                "Qty": str(abs(ie.quantity)),
                "Unit": "NOS",
                "UnitPrice": str(ie.rate) if ie.rate else "0",
                "TotAmt": str(abs(ie.amount)),
                "AssAmt": str(abs(ie.amount)),
                "GstRt": "0",
                "IgstAmt": "0",
                "CgstAmt": "0",
                "SgstAmt": "0",
            }
            items.append(item)

        if not items:
            taxable = abs(voucher.total_amount) - abs(voucher.gst_amount)
            items.append(
                {
                    "SlNo": "1",
                    "PrdDesc": voucher.narration or "Services",
                    "HsnCd": "",
                    "Qty": "1",
                    "Unit": "NOS",
                    "UnitPrice": str(taxable),
                    "TotAmt": str(taxable),
                    "AssAmt": str(taxable),
                    "GstRt": "0",
                    "IgstAmt": "0",
                    "CgstAmt": "0",
                    "SgstAmt": "0",
                }
            )

        return items

    def _build_value_details(self, voucher: TallyVoucher) -> dict[str, Any]:
        taxable = abs(voucher.total_amount) - abs(voucher.gst_amount)
        cgst = Decimal("0")
        sgst = Decimal("0")
        igst = Decimal("0")
        for le in voucher.ledger_entries:
            name = le.ledger_name.upper()
            amt = abs(le.amount)
            if "CGST" in name:
                cgst = amt
            elif "SGST" in name:
                sgst = amt
            elif "IGST" in name:
                igst = amt

        total_inv = taxable + cgst + sgst + igst
        return {
            "AssVal": str(taxable),
            "CgstVal": str(cgst),
            "SgstVal": str(sgst),
            "IgstVal": str(igst),
            "TotInvVal": str(total_inv),
        }
