"""Report models — see SPECS.md §3c."""

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

TallyReportType = Literal[
    "Balance Sheet",
    "Profit & Loss",
    "Trial Balance",
    "Day Book",
    "GSTR-3B",
    "GSTR-1",
    "GSTR-2A",
    "GSTR-9",
    "Unknown",
]


class TrialBalanceLine(BaseModel):
    ledger: str
    group: str
    opening_debit: Decimal = Decimal("0")
    opening_credit: Decimal = Decimal("0")
    period_debit: Decimal = Decimal("0")
    period_credit: Decimal = Decimal("0")
    closing_debit: Decimal = Decimal("0")
    closing_credit: Decimal = Decimal("0")


class OutstandingBill(BaseModel):
    party_name: str
    bill_date: date
    bill_number: str
    bill_amount: Decimal
    paid_amount: Decimal = Decimal("0")
    outstanding_amount: Decimal
    overdue_days: int = 0
    voucher_type: str


class DailyDigest(BaseModel):
    company: str
    digest_date: date
    total_sales: Decimal = Decimal("0")
    total_purchases: Decimal = Decimal("0")
    cash_balance: Decimal = Decimal("0")
    bank_balance: Decimal = Decimal("0")
    top_overdue_receivables: list[OutstandingBill] = []
    gst_filings_due: list[str] = []
    low_stock_items: list[str] = []


class StockAgingLine(BaseModel):
    """One row in a stock aging report."""

    item_name: str
    unit: str
    closing_quantity: Decimal
    closing_value: Decimal
    last_movement_date: date | None = None
    days_since_movement: int = 0
    aging_bucket: str = ""


class SyncResult(BaseModel):
    entity_type: str
    records_synced: int = 0
    alter_id_before: int = 0
    alter_id_after: int = 0
    duration_seconds: float = 0.0
    success: bool = True
    error_message: str | None = None


class ReportLine(BaseModel):
    """One line item in a Balance Sheet or P&L report."""

    name: str
    closing_debit: Decimal = Decimal("0")
    closing_credit: Decimal = Decimal("0")


class TallyReport(BaseModel):
    """Parsed result from a Tally TYPE=Data report export."""

    report_type: TallyReportType
    from_date: date | None = None
    to_date: date | None = None
    lines: list[ReportLine] = []
    trial_balance: list[TrialBalanceLine] = []
    vouchers: list[dict[str, object]] = []


class ImportResult(BaseModel):
    """Result of an import operation (masters or vouchers) into TallyPrime."""

    success: bool = True
    created: int = 0
    altered: int = 0
    deleted: int = 0
    errors: int = 0
    error_messages: list[str] = []
    raw_response: str = ""


class GSTR3BSection(BaseModel):
    """One section of the GSTR-3B return."""

    section: str
    description: str = ""
    taxable_value: Decimal = Decimal("0")
    integrated_tax: Decimal = Decimal("0")
    central_tax: Decimal = Decimal("0")
    state_tax: Decimal = Decimal("0")
    cess: Decimal = Decimal("0")


class GSTR3BResult(BaseModel):
    """Parsed GSTR-3B return data from TallyPrime."""

    from_date: date | None = None
    to_date: date | None = None
    gstin: str = ""
    sections: list[GSTR3BSection] = []
    raw_response: str = ""


class ValidationResult(BaseModel):
    """Result of pre-write validation."""

    valid: bool = True
    errors: list[str] = []
    warnings: list[str] = []


class GSTR2AClaim(BaseModel):
    """One ITC claim line from GSTR-2A/2B."""

    supplier_gstin: str = ""
    supplier_name: str = ""
    invoice_number: str = ""
    invoice_date: date | None = None
    taxable_value: Decimal = Decimal("0")
    cgst: Decimal = Decimal("0")
    sgst: Decimal = Decimal("0")
    igst: Decimal = Decimal("0")
    cess: Decimal = Decimal("0")
    itc_available: Decimal = Decimal("0")
    supply_type: str = ""


class ReconciliationResult(BaseModel):
    """Result of ITC reconciliation."""

    total_2a_claims: int = 0
    matched: int = 0
    mismatched: int = 0
    missing_in_tally: int = 0
    missing_in_2a: int = 0
    itc_claimed: Decimal = Decimal("0")
    itc_available: Decimal = Decimal("0")
    mismatches: list[dict[str, Any]] = []


class GSTR1Invoice(BaseModel):
    """A single invoice within a GSTR-1 section."""

    invoice_number: str = ""
    invoice_date: date | None = None
    party_gstin: str = ""
    party_name: str = ""
    place_of_supply: str = ""
    reverse_charge: bool = False
    invoice_type: str = ""
    taxable_value: Decimal = Decimal("0")
    cgst: Decimal = Decimal("0")
    sgst: Decimal = Decimal("0")
    igst: Decimal = Decimal("0")
    cess: Decimal = Decimal("0")
    hsn_code: str = ""
    supply_type: str = ""


class GSTR1Section(BaseModel):
    """One section of the GSTR-1 return (B2B, B2CL, B2CS, CDNR, CDNUR, HSN, etc.)."""

    section: str
    description: str = ""
    invoices: list[GSTR1Invoice] = []
    taxable_value: Decimal = Decimal("0")
    cgst: Decimal = Decimal("0")
    sgst: Decimal = Decimal("0")
    igst: Decimal = Decimal("0")
    cess: Decimal = Decimal("0")


class GSTR1Result(BaseModel):
    """Parsed GSTR-1 return data from TallyPrime."""

    from_date: date | None = None
    to_date: date | None = None
    gstin: str = ""
    sections: list[GSTR1Section] = []
    raw_response: str = ""


class GSTR9Section(BaseModel):
    """One section of the GSTR-9 annual return."""

    section: str
    description: str = ""
    taxable_value: Decimal = Decimal("0")
    integrated_tax: Decimal = Decimal("0")
    central_tax: Decimal = Decimal("0")
    state_tax: Decimal = Decimal("0")
    cess: Decimal = Decimal("0")


class GSTR9Result(BaseModel):
    """Parsed GSTR-9 annual return data from TallyPrime."""

    from_date: date | None = None
    to_date: date | None = None
    gstin: str = ""
    sections: list[GSTR9Section] = []
    raw_response: str = ""
