"""Report models — see SPECS.md §3c."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


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
