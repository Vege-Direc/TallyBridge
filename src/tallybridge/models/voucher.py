"""Voucher models — see SPECS.md §3b."""

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field


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


class TallyCostCentreAllocation(BaseModel):
    ledger_name: str
    cost_centre: str
    amount: Decimal


class TallyBillAllocation(BaseModel):
    ledger_name: str
    bill_name: str
    amount: Decimal
    bill_type: str | None = None
    bill_credit_period: int | None = None


class TallyVoucher(BaseModel):
    guid: str
    alter_id: int
    voucher_number: str
    voucher_type: str
    date: date_type
    effective_date: date_type | None = None
    reference: str | None = None
    narration: str | None = None
    is_cancelled: bool = False
    is_optional: bool = False
    is_postdated: bool = False
    is_void: bool = False
    party_ledger: str | None = None
    party_gstin: str | None = None
    place_of_supply: str | None = None
    due_date: date_type | None = None
    entered_by: str | None = None
    ledger_entries: list[TallyVoucherEntry] = Field(default_factory=list)
    inventory_entries: list[TallyInventoryEntry] = Field(default_factory=list)
    cost_centre_allocations: list[TallyCostCentreAllocation] = Field(
        default_factory=list
    )
    bill_allocations: list[TallyBillAllocation] = Field(default_factory=list)
    total_amount: Decimal = Decimal("0")
    gst_amount: Decimal = Decimal("0")
