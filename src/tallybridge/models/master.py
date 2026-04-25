"""Master data models — see SPECS.md §3a."""

from decimal import Decimal

from pydantic import BaseModel


class TallyLedger(BaseModel):
    name: str
    guid: str
    alter_id: int
    parent_group: str
    opening_balance: Decimal = Decimal("0")
    closing_balance: Decimal = Decimal("0")
    is_revenue: bool = False
    affects_gross_profit: bool = False
    gstin: str | None = None
    party_name: str | None = None
    bill_credit_period: int | None = None


class TallyGroup(BaseModel):
    name: str
    guid: str
    alter_id: int
    parent: str
    primary_group: str
    is_revenue: bool = False
    affects_gross_profit: bool = False
    net_debit_credit: str = "Dr"


class TallyStockItem(BaseModel):
    name: str
    guid: str
    alter_id: int
    parent_group: str
    unit: str
    gst_rate: Decimal | None = None
    hsn_code: str | None = None
    opening_quantity: Decimal = Decimal("0")
    opening_rate: Decimal = Decimal("0")
    closing_quantity: Decimal = Decimal("0")
    closing_value: Decimal = Decimal("0")


class TallyGodown(BaseModel):
    name: str
    guid: str
    alter_id: int
    parent: str | None = None


class TallyVoucherType(BaseModel):
    name: str
    guid: str
    alter_id: int
    parent: str
    number_series: str | None = None


class TallyUnit(BaseModel):
    """Unit of measure — Nos, Kgs, Ltrs, Boxes, etc."""

    name: str
    guid: str
    alter_id: int
    unit_type: str = "Simple"
    base_units: str | None = None
    decimal_places: int = 0
    symbol: str | None = None


class TallyStockGroup(BaseModel):
    """Parent grouping for stock items — mirrors TallyGroup for ledgers."""

    name: str
    guid: str
    alter_id: int
    parent: str
    should_quantities_add: bool = True


class TallyCostCenter(BaseModel):
    """Cost centre for department/project-wise tracking.

    Most Indian businesses use cost centres to split P&L by department,
    project, or branch. Required for cost-centre-wise reports.
    """

    name: str
    guid: str
    alter_id: int
    parent: str
    email: str | None = None
    cost_centre_type: str = "Primary"
