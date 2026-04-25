"""Voucher models — see SPECS.md §3b."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class TallyVoucherEntry(BaseModel):
    ledger_name: str
    amount: Decimal


class TallyInventoryEntry(BaseModel):
    stock_item_name: str
    quantity: Decimal = Decimal("0")
    rate: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    godown: str | None = None
    batch: str | None = None


class TallyVoucher(BaseModel):
    guid: str
    alter_id: int
    voucher_number: str
    voucher_type: str
    date: date
    effective_date: date | None = None
    reference: str | None = None
    narration: str | None = None
    is_cancelled: bool = False
    is_optional: bool = False
    is_postdated: bool = False
    is_void: bool = False
    party_ledger: str | None = None
    party_gstin: str | None = None
    place_of_supply: str | None = None
    due_date: date | None = None
    entered_by: str | None = None
    ledger_entries: list[TallyVoucherEntry] = []
    inventory_entries: list[TallyInventoryEntry] = []
    total_amount: Decimal = Decimal("0")
    gst_amount: Decimal = Decimal("0")
