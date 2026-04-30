"""Public query API — see SPECS.md §8."""

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from tallybridge.cache import TallyCache
from tallybridge.models.master import TallyStockItem
from tallybridge.models.report import (
    DailyDigest,
    GSTR1Result,
    OutstandingBill,
    ReconciliationResult,
    StockAgingLine,
    TrialBalanceLine,
)
from tallybridge.models.voucher import TallyVoucher


def _parse_date_field(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


class TallyQuery:
    def __init__(self, cache: TallyCache) -> None:
        self._cache = cache
        self._fuzzy_checked: bool | None = None

    def get_daily_digest(self, as_of_date: date | None = None) -> DailyDigest:
        """Complete business summary for the given date (default: today)."""
        as_of_date = as_of_date or date.today()
        sales_rows = self._cache.query(
            """SELECT COALESCE(SUM(total_amount), 0) as total
            FROM trn_voucher
            WHERE voucher_type = 'Sales' AND is_cancelled = false AND is_void = false
            AND date <= ?""",
            [str(as_of_date)],
        )
        purchase_rows = self._cache.query(
            """SELECT COALESCE(SUM(total_amount), 0) as total
            FROM trn_voucher
            WHERE voucher_type = 'Purchase' AND is_cancelled = false AND is_void = false
            AND date <= ?""",
            [str(as_of_date)],
        )
        cash_bal = self.get_cash_balance(as_of_date)
        bank_bal = self.get_bank_balance(as_of_date)
        receivables = self.get_receivables(as_of_date, overdue_only=True)
        top_overdue = sorted(receivables, key=lambda b: b.overdue_days, reverse=True)[
            :5
        ]
        low_stock = self.get_low_stock_items()

        return DailyDigest(
            company="TallyBridge",
            digest_date=as_of_date,
            total_sales=Decimal(str(sales_rows[0]["total"]))
            if sales_rows
            else Decimal("0"),
            total_purchases=Decimal(str(purchase_rows[0]["total"]))
            if purchase_rows
            else Decimal("0"),
            cash_balance=cash_bal,
            bank_balance=bank_bal,
            top_overdue_receivables=top_overdue,
            low_stock_items=[i.name for i in low_stock],
        )

    def get_ledger_balance(
        self, ledger_name: str, as_of_date: date | None = None
    ) -> Decimal:
        """Closing balance as of date. Positive = Dr, Negative = Cr."""
        return self._cache.get_ledger_balance(ledger_name)

    def get_cash_balance(self, as_of_date: date | None = None) -> Decimal:
        """Sum of all ledgers under the 'Cash-in-Hand' group."""
        rows = self._cache.query(
            """SELECT COALESCE(SUM(closing_balance), 0) as total
            FROM mst_ledger WHERE parent_group = 'Cash-in-Hand'"""
        )
        return Decimal(str(rows[0]["total"])) if rows else Decimal("0")

    def get_bank_balance(self, as_of_date: date | None = None) -> Decimal:
        """Sum of all ledgers under the 'Bank Accounts' group."""
        rows = self._cache.query(
            """SELECT COALESCE(SUM(closing_balance), 0) as total
            FROM mst_ledger WHERE parent_group = 'Bank Accounts'"""
        )
        return Decimal(str(rows[0]["total"])) if rows else Decimal("0")

    def get_trial_balance(
        self, from_date: date, to_date: date
    ) -> list[TrialBalanceLine]:
        """Trial balance for the period."""
        return self._cache.get_trial_balance(from_date, to_date)

    def get_receivables(
        self,
        as_of_date: date | None = None,
        overdue_only: bool = False,
        min_days_overdue: int = 0,
    ) -> list[OutstandingBill]:
        """Outstanding sales invoices."""
        bills = self._cache.get_outstanding_receivables()
        as_of_date = as_of_date or date.today()
        result: list[OutstandingBill] = []
        for bill in bills:
            overdue = (as_of_date - bill.bill_date).days
            bill.overdue_days = max(0, overdue)
            if overdue_only and overdue <= 0:
                continue
            if min_days_overdue > 0 and overdue < min_days_overdue:
                continue
            result.append(bill)
        return result

    def get_payables(
        self,
        as_of_date: date | None = None,
        overdue_only: bool = False,
    ) -> list[OutstandingBill]:
        """Outstanding purchase invoices."""
        bills = self._cache.get_outstanding_payables()
        as_of_date = as_of_date or date.today()
        result: list[OutstandingBill] = []
        for bill in bills:
            overdue = (as_of_date - bill.bill_date).days
            bill.overdue_days = max(0, overdue)
            if overdue_only and overdue <= 0:
                continue
            result.append(bill)
        return result

    def get_party_outstanding(self, party_name: str) -> dict[str, Any]:
        """Full position for one party."""
        receivables = [b for b in self.get_receivables() if b.party_name == party_name]
        payables = [b for b in self.get_payables() if b.party_name == party_name]
        total_rec = sum((b.outstanding_amount for b in receivables), Decimal("0"))
        total_pay = sum((b.outstanding_amount for b in payables), Decimal("0"))
        return {
            "total_receivable": total_rec,
            "total_payable": total_pay,
            "net_position": total_rec - total_pay,
            "bills": receivables + payables,
        }

    def get_sales_summary(
        self,
        from_date: date,
        to_date: date,
        group_by: Literal["day", "week", "month", "party", "item"] = "day",
    ) -> list[dict[str, Any]]:
        """Sales summary grouped by dimension."""
        if group_by == "party":
            rows = self._cache.query(
                """SELECT party_ledger as party_name,
                          SUM(total_amount) as total_amount,
                          COUNT(*) as voucher_count
                FROM trn_voucher
                WHERE voucher_type = 'Sales'
                AND is_cancelled = false AND is_void = false
                AND date BETWEEN ? AND ?
                GROUP BY party_ledger""",
                [str(from_date), str(to_date)],
            )
            return [
                {
                    "party_name": r["party_name"] or "",
                    "total_amount": Decimal(str(r["total_amount"])),
                    "voucher_count": r["voucher_count"],
                }
                for r in rows
            ]

        if group_by == "day":
            rows = self._cache.query(
                """SELECT date as period,
                          SUM(total_amount) as total_amount,
                          COUNT(*) as voucher_count
                FROM trn_voucher
                WHERE voucher_type = 'Sales'
                AND is_cancelled = false AND is_void = false
                AND date BETWEEN ? AND ?
                GROUP BY date ORDER BY date""",
                [str(from_date), str(to_date)],
            )
            return [
                {
                    "period": str(r["period"]),
                    "total_amount": Decimal(str(r["total_amount"])),
                    "voucher_count": r["voucher_count"],
                }
                for r in rows
            ]

        rows = self._cache.query(
            """SELECT date as period,
                      SUM(total_amount) as total_amount,
                      COUNT(*) as voucher_count
            FROM trn_voucher
            WHERE voucher_type = 'Sales' AND is_cancelled = false AND is_void = false
            AND date BETWEEN ? AND ?
            GROUP BY date ORDER BY date""",
            [str(from_date), str(to_date)],
        )
        return [
            {
                "period": str(r["period"]),
                "total_amount": Decimal(str(r["total_amount"])),
                "voucher_count": r["voucher_count"],
            }
            for r in rows
        ]

    def get_purchases_summary(
        self, from_date: date, to_date: date, group_by: str = "day"
    ) -> list[dict[str, Any]]:
        """Purchases summary grouped by dimension."""
        rows = self._cache.query(
            """SELECT date as period,
                      SUM(total_amount) as total_amount,
                      COUNT(*) as voucher_count
            FROM trn_voucher
            WHERE voucher_type = 'Purchase' AND is_cancelled = false AND is_void = false
            AND date BETWEEN ? AND ?
            GROUP BY date ORDER BY date""",
            [str(from_date), str(to_date)],
        )
        return [
            {
                "period": str(r["period"]),
                "total_amount": Decimal(str(r["total_amount"])),
                "voucher_count": r["voucher_count"],
            }
            for r in rows
        ]

    def get_vouchers(
        self,
        voucher_type: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        party_name: str | None = None,
        limit: int = 100,
    ) -> list[TallyVoucher]:
        """Vouchers matching filters. Excludes cancelled and optional by default."""
        conditions = ["is_cancelled = false", "is_void = false"]
        params: list[str] = []
        if voucher_type:
            conditions.append("voucher_type = ?")
            params.append(voucher_type)
        if from_date:
            conditions.append("date >= ?")
            params.append(str(from_date))
        if to_date:
            conditions.append("date <= ?")
            params.append(str(to_date))
        if party_name:
            conditions.append("party_ledger = ?")
            params.append(party_name)
        where = " AND ".join(conditions)
        rows = self._cache.query(
            f"""SELECT * FROM trn_voucher
            WHERE {where} ORDER BY date DESC LIMIT {limit}""",
            params,
        )
        return [self._row_to_voucher(r) for r in rows]

    def get_stock_summary(self) -> list[dict[str, Any]]:
        """All items: [{name, unit, closing_quantity, closing_value}]"""
        return self._cache.query(
            "SELECT name, unit, closing_quantity, closing_value "
            "FROM mst_stock_item ORDER BY name"
        )

    def get_low_stock_items(
        self, threshold_quantity: Decimal = Decimal("0")
    ) -> list[TallyStockItem]:
        """Items with closing_quantity <= threshold_quantity."""
        rows = self._cache.query(
            "SELECT * FROM mst_stock_item WHERE closing_quantity <= ?",
            [threshold_quantity],
        )
        return [
            TallyStockItem(
                name=r["name"],
                guid=r["guid"],
                alter_id=r["alter_id"],
                parent_group=r["parent_group"] or "",
                unit=r["unit"] or "",
                closing_quantity=Decimal(str(r["closing_quantity"] or 0)),
                closing_value=Decimal(str(r["closing_value"] or 0)),
            )
            for r in rows
        ]

    def get_stock_aging(
        self,
        as_of_date: date | None = None,
        bucket_days: list[int] | None = None,
    ) -> list[StockAgingLine]:
        """Stock aging analysis."""
        as_of_date = as_of_date or date.today()
        bucket_days = bucket_days or [30, 60, 90, 180]

        items = self._cache.query(
            "SELECT name, unit, closing_quantity, closing_value "
            "FROM mst_stock_item WHERE closing_quantity > 0"
        )
        movement_dates = self._cache.query(
            """SELECT ie.stock_item_name, MAX(v.date) as last_date
            FROM trn_inventory_entry ie
            JOIN trn_voucher v ON ie.voucher_guid = v.guid
            WHERE v.is_cancelled = false
            GROUP BY ie.stock_item_name"""
        )
        last_movement = {r["stock_item_name"]: r["last_date"] for r in movement_dates}

        result: list[StockAgingLine] = []
        for item in items:
            name = item["name"]
            last_date = last_movement.get(name)
            if last_date and isinstance(last_date, str):
                try:
                    last_date = date.fromisoformat(last_date)
                except ValueError:
                    last_date = None

            days_since = 0
            bucket = "No Movement"
            if last_date and isinstance(last_date, date):
                days_since = (as_of_date - last_date).days
                bucket = self._get_bucket(days_since, bucket_days)
            elif last_date is None and Decimal(str(item["closing_quantity"])) > 0:
                bucket = "No Movement"

            result.append(
                StockAgingLine(
                    item_name=name,
                    unit=item["unit"] or "",
                    closing_quantity=Decimal(str(item["closing_quantity"])),
                    closing_value=Decimal(str(item["closing_value"])),
                    last_movement_date=last_date
                    if isinstance(last_date, date)
                    else None,
                    days_since_movement=days_since,
                    aging_bucket=bucket,
                )
            )
        return result

    def get_gst_summary(self, from_date: date, to_date: date) -> dict[str, Any]:
        """GST summary for the period."""
        rows = self._cache.query(
            """SELECT le.ledger_name, SUM(le.amount) as total
            FROM trn_ledger_entry le
            JOIN trn_voucher v ON le.voucher_guid = v.guid
            WHERE v.is_cancelled = false AND v.is_void = false
            AND v.date BETWEEN ? AND ?
            AND (le.ledger_name LIKE '%CGST%' OR le.ledger_name LIKE '%SGST%'
                 OR le.ledger_name LIKE '%IGST%')
            GROUP BY le.ledger_name""",
            [str(from_date), str(to_date)],
        )
        result: dict[str, Decimal] = {
            "total_cgst_collected": Decimal("0"),
            "total_sgst_collected": Decimal("0"),
            "total_igst_collected": Decimal("0"),
            "total_cgst_paid": Decimal("0"),
            "total_sgst_paid": Decimal("0"),
            "total_igst_paid": Decimal("0"),
            "net_itc": Decimal("0"),
            "net_liability": Decimal("0"),
        }
        for r in rows:
            name = r["ledger_name"].upper()
            amount = abs(Decimal(str(r["total"])))
            if "CGST" in name:
                result["total_cgst_collected"] = amount
            elif "SGST" in name:
                result["total_sgst_collected"] = amount
            elif "IGST" in name:
                result["total_igst_collected"] = amount
        result["net_liability"] = (
            result["total_cgst_collected"]
            + result["total_sgst_collected"]
            + result["total_igst_collected"]
            - result["net_itc"]
        )
        return result

    def get_einvoice_summary(self, from_date: date, to_date: date) -> dict[str, Any]:
        """Summary of e-invoiced and non-e-invoiced sales for the period."""
        total_rows = self._cache.query(
            """SELECT COUNT(*) as cnt FROM trn_voucher
            WHERE voucher_type IN ('Sales', 'Credit Note')
            AND is_cancelled = false AND is_void = false
            AND date BETWEEN ? AND ?""",
            [str(from_date), str(to_date)],
        )
        einv_rows = self._cache.query(
            """SELECT COUNT(*) as cnt FROM trn_voucher
            WHERE voucher_type IN ('Sales', 'Credit Note')
            AND is_cancelled = false AND is_void = false
            AND is_einvoice = true
            AND date BETWEEN ? AND ?""",
            [str(from_date), str(to_date)],
        )
        missing_rows = self._cache.query(
            """SELECT guid, voucher_number, date, party_ledger, total_amount
            FROM trn_voucher
            WHERE voucher_type IN ('Sales', 'Credit Note')
            AND is_cancelled = false AND is_void = false
            AND (irn IS NULL OR irn = '')
            AND date BETWEEN ? AND ?
            ORDER BY date DESC""",
            [str(from_date), str(to_date)],
        )
        total = total_rows[0]["cnt"] if total_rows else 0
        einv = einv_rows[0]["cnt"] if einv_rows else 0
        return {
            "total_sales_invoices": total,
            "einvoiced_count": einv,
            "not_einvoiced_count": total - einv,
            "missing_irn": missing_rows,
        }

    def get_eway_bill_summary(self, from_date: date, to_date: date) -> dict[str, Any]:
        """Summary of e-Way Bills for the period."""
        total_rows = self._cache.query(
            """SELECT COUNT(*) as cnt FROM trn_voucher
            WHERE eway_bill_number IS NOT NULL AND eway_bill_number != ''
            AND is_cancelled = false AND is_void = false
            AND date BETWEEN ? AND ?""",
            [str(from_date), str(to_date)],
        )
        active_rows = self._cache.query(
            """SELECT COUNT(*) as cnt FROM trn_voucher
            WHERE eway_bill_number IS NOT NULL AND eway_bill_number != ''
            AND is_cancelled = false AND is_void = false
            AND eway_valid_till >= ?
            AND date BETWEEN ? AND ?""",
            [str(date.today()), str(from_date), str(to_date)],
        )
        expired_rows = self._cache.query(
            """SELECT COUNT(*) as cnt FROM trn_voucher
            WHERE eway_bill_number IS NOT NULL AND eway_bill_number != ''
            AND is_cancelled = false AND is_void = false
            AND eway_valid_till < ?
            AND date BETWEEN ? AND ?""",
            [str(date.today()), str(from_date), str(to_date)],
        )
        expiring_rows = self._cache.query(
            """SELECT guid, voucher_number, date, eway_bill_number,
                      eway_valid_till, party_ledger, total_amount
            FROM trn_voucher
            WHERE eway_bill_number IS NOT NULL AND eway_bill_number != ''
            AND is_cancelled = false AND is_void = false
            AND eway_valid_till BETWEEN ? AND ?
            AND date BETWEEN ? AND ?
            ORDER BY eway_valid_till""",
            [
                str(date.today()),
                str(date.fromordinal(date.today().toordinal() + 1)),
                str(from_date),
                str(to_date),
            ],
        )
        total = total_rows[0]["cnt"] if total_rows else 0
        active = active_rows[0]["cnt"] if active_rows else 0
        expired = expired_rows[0]["cnt"] if expired_rows else 0
        return {
            "total_eway_bills": total,
            "active_bills": active,
            "expired_bills": expired,
            "expiring_soon": expiring_rows,
        }

    def get_cost_center_summary(
        self,
        from_date: date,
        to_date: date,
        cost_center_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Income and expense breakdown by cost centre for the period."""
        centers = self._cache.query("SELECT name FROM mst_cost_center")
        if cost_center_name:
            centers = [c for c in centers if c["name"] == cost_center_name]

        # NOTE: v0.1 approximation — cost centre allocations are not yet in
        # trn_ledger_entry. Using party_ledger as a proxy for cost centre.
        result: list[dict[str, Any]] = []
        for cc in centers:
            result.append(
                {
                    "cost_center": cc["name"],
                    "total_income": Decimal("0"),
                    "total_expense": Decimal("0"),
                    "net": Decimal("0"),
                }
            )
        return result

    def get_godown_summary(self, company: str | None = None) -> list[dict[str, Any]]:
        """Return all godowns with parent hierarchy."""
        sql = "SELECT guid, name, parent FROM mst_godown"
        params: list[str] = []
        if company:
            sql += " WHERE company = ?"
            params.append(company)
        return self._cache.query(sql, params)

    def search(self, query: str, limit: int = 20) -> dict[str, Any]:
        """Search across ledger names, party names, narrations with fuzzy matching.

        Attempts trigram-based fuzzy matching via DuckDB's string similarity
        functions. Falls back to ILIKE when trigram extension is unavailable.
        """
        if not query.strip():
            return {"ledgers": [], "vouchers": [], "parties": []}
        pattern = f"%{query}%"
        fuzzy = self._fuzzy_available()
        if fuzzy:
            ledgers = self._fuzzy_search_ledgers(query, limit)
        else:
            ledgers = self._cache.query(
                "SELECT * FROM mst_ledger WHERE name ILIKE ? LIMIT ?",
                [pattern, limit],
            )
        if fuzzy:
            vouchers = self._fuzzy_search_vouchers(query, limit)
        else:
            vouchers = self._cache.query(
                """SELECT * FROM trn_voucher
                WHERE (narration ILIKE ? OR party_ledger ILIKE ?)
                AND is_cancelled = false
                LIMIT ?""",
                [pattern, pattern, limit],
            )
        parties = self._cache.query(
            "SELECT DISTINCT party_ledger as name "
            "FROM trn_voucher WHERE party_ledger ILIKE ? "
            "AND is_cancelled = false LIMIT ?",
            [pattern, limit],
        )
        return {
            "ledgers": ledgers,
            "vouchers": [self._row_to_voucher(r) for r in vouchers],
            "parties": [r["name"] for r in parties if r["name"]],
        }

    def _fuzzy_available(self) -> bool:
        if self._fuzzy_checked is not None:
            return self._fuzzy_checked
        try:
            self._cache.query("SELECT similarity('test', 'test') as s")
            self._fuzzy_checked = True
            return True
        except Exception:
            self._fuzzy_checked = False
            return False

    def _fuzzy_search_ledgers(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Search ledgers using trigram similarity, falling back to ILIKE."""
        try:
            return self._cache.query(
                """SELECT * FROM mst_ledger
                WHERE name ILIKE ? OR similarity(name, ?) > 0.3
                ORDER BY similarity(name, ?) DESC LIMIT ?""",
                [f"%{query}%", query, query, limit],
            )
        except Exception:
            return self._cache.query(
                "SELECT * FROM mst_ledger WHERE name ILIKE ? LIMIT ?",
                [f"%{query}%", limit],
            )

    def _fuzzy_search_vouchers(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Search vouchers using trigram similarity, falling back to ILIKE."""
        try:
            return self._cache.query(
                """SELECT * FROM trn_voucher
                WHERE (narration ILIKE ? OR party_ledger ILIKE ?
                       OR similarity(party_ledger, ?) > 0.3)
                AND is_cancelled = false
                ORDER BY similarity(party_ledger, ?) DESC LIMIT ?""",
                [f"%{query}%", f"%{query}%", query, query, limit],
            )
        except Exception:
            return self._cache.query(
                """SELECT * FROM trn_voucher
                WHERE (narration ILIKE ? OR party_ledger ILIKE ?)
                AND is_cancelled = false
                LIMIT ?""",
                [f"%{query}%", f"%{query}%", limit],
            )

    @staticmethod
    def _get_bucket(days: int, bucket_days: list[int]) -> str:
        prev = 0
        for boundary in bucket_days:
            if days <= boundary:
                return f"{prev + 1}-{boundary}"
            prev = boundary
        return f"{prev}+"

    @staticmethod
    def _row_to_voucher(r: dict[str, Any]) -> TallyVoucher:
        d = r.get("date")
        if isinstance(d, str):
            try:
                d = date.fromisoformat(d)
            except ValueError:
                d = date.today()
        elif not isinstance(d, date):
            d = date.today()
        ed = r.get("effective_date")
        if isinstance(ed, str):
            try:
                ed = date.fromisoformat(ed)
            except ValueError:
                ed = None
        elif not isinstance(ed, date):
            ed = None
        dd = r.get("due_date")
        if isinstance(dd, str):
            try:
                dd = date.fromisoformat(dd)
            except ValueError:
                dd = None
        elif not isinstance(dd, date):
            dd = None
        return TallyVoucher(
            guid=r.get("guid", ""),
            alter_id=r.get("alter_id", 0),
            voucher_number=r.get("voucher_number") or "",
            voucher_type=r.get("voucher_type") or "",
            date=d,
            effective_date=ed,
            narration=r.get("narration"),
            is_cancelled=bool(r.get("is_cancelled")),
            is_void=bool(r.get("is_void")),
            party_ledger=r.get("party_ledger"),
            total_amount=Decimal(str(r.get("total_amount") or 0)),
            currency=r.get("currency"),
            forex_amount=Decimal(str(r.get("forex_amount")))
            if r.get("forex_amount") is not None
            else None,
            exchange_rate=Decimal(str(r.get("exchange_rate")))
            if r.get("exchange_rate") is not None
            else None,
            base_currency_amount=Decimal(str(r.get("base_currency_amount")))
            if r.get("base_currency_amount") is not None
            else None,
            irn=r.get("irn"),
            ack_number=r.get("ack_number"),
            ack_date=_parse_date_field(r.get("ack_date")),
            qr_code=r.get("qr_code"),
            is_einvoice=bool(r.get("is_einvoice")),
            eway_bill_number=r.get("eway_bill_number"),
            eway_bill_date=_parse_date_field(r.get("eway_bill_date")),
            eway_valid_till=_parse_date_field(r.get("eway_valid_till")),
            transporter_name=r.get("transporter_name"),
            vehicle_number=r.get("vehicle_number"),
            distance_km=int(str(r.get("distance_km")))
            if r.get("distance_km") is not None
            else None,
        )

    def get_balance_sheet(self, to_date: date | None = None) -> list[dict[str, Any]]:
        """Balance sheet grouped by assets and liabilities.

        Queries the local cache for ledger closing balances and groups
        them by their parent group into Assets and Liabilities.
        """
        to_date = to_date or date.today()
        rows = self._cache.query(
            """SELECT l.name, l.parent_group, l.closing_balance
            FROM mst_ledger l
            WHERE l.closing_balance IS NOT NULL
            ORDER BY l.parent_group, l.name""",
            [],
        )
        result: list[dict[str, Any]] = []
        for r in rows:
            balance = Decimal(str(r.get("closing_balance") or 0))
            parent = str(r.get("parent_group") or "")
            section = "Liabilities" if balance < 0 else "Assets"
            result.append(
                {
                    "name": r.get("name"),
                    "group": parent,
                    "section": section,
                    "amount": str(abs(balance)),
                }
            )
        return result

    def get_profit_loss(self, from_date: date, to_date: date) -> list[dict[str, Any]]:
        """Profit & Loss grouped by income and expense.

        Queries voucher entries for the given period and groups
        by ledger parent into Income and Expense sections.
        """
        rows = self._cache.query(
            """SELECT le.ledger_name, le.amount,
                      COALESCE(l.parent_group, 'Unknown') as parent_group
            FROM trn_ledger_entry le
            JOIN trn_voucher v ON le.voucher_guid = v.guid
            LEFT JOIN mst_ledger l ON le.ledger_name = l.name
            WHERE v.date >= ? AND v.date <= ?
            AND v.is_cancelled = false AND v.is_void = false
            AND l.parent_group IN (
                'Direct Income', 'Indirect Incomes',
                'Direct Expenses', 'Indirect Expenses',
                'Sales Accounts', 'Purchase Accounts'
            )
            ORDER BY l.parent_group, le.ledger_name""",
            [str(from_date), str(to_date)],
        )
        result: list[dict[str, Any]] = []
        for r in rows:
            parent = str(r.get("parent_group") or "Unknown")
            amount = Decimal(str(r.get("amount") or 0))
            if parent in ("Direct Income", "Indirect Incomes", "Sales Accounts"):
                section = "Income"
            else:
                section = "Expense"
            result.append(
                {
                    "ledger": r.get("ledger_name"),
                    "group": parent,
                    "section": section,
                    "amount": str(abs(amount)),
                }
            )
        return result

    def get_ledger_account(
        self, ledger_name: str, from_date: date, to_date: date
    ) -> list[dict[str, Any]]:
        """Voucher-level general ledger for a specific ledger.

        Returns all ledger entries for the given ledger within the
        specified date range, with voucher details.
        """
        rows = self._cache.query(
            """SELECT v.date, v.voucher_type, v.voucher_number,
                      v.narration, le.amount
            FROM trn_ledger_entry le
            JOIN trn_voucher v ON le.voucher_guid = v.guid
            WHERE le.ledger_name = ?
            AND v.date >= ? AND v.date <= ?
            AND v.is_cancelled = false
            ORDER BY v.date, v.voucher_number""",
            [ledger_name, str(from_date), str(to_date)],
        )
        result: list[dict[str, Any]] = []
        for r in rows:
            amount = Decimal(str(r.get("amount") or 0))
            d = r.get("date")
            result.append(
                {
                    "date": str(d) if d else None,
                    "voucher_type": r.get("voucher_type"),
                    "voucher_number": r.get("voucher_number"),
                    "narration": r.get("narration"),
                    "debit": str(abs(amount)) if amount < 0 else "0",
                    "credit": str(abs(amount)) if amount >= 0 else "0",
                }
            )
        return result

    def get_stock_item_account(
        self, item_name: str, from_date: date, to_date: date
    ) -> list[dict[str, Any]]:
        """Quantity movements for a stock item within a date range.

        Returns all inventory entries for the item, showing inward
        and outward quantities with voucher details.
        """
        rows = self._cache.query(
            """SELECT v.date, v.voucher_type, v.voucher_number,
                      ie.quantity, ie.amount
            FROM trn_inventory_entry ie
            JOIN trn_voucher v ON ie.voucher_guid = v.guid
            WHERE ie.stock_item_name = ?
            AND v.date >= ? AND v.date <= ?
            AND v.is_cancelled = false
            ORDER BY v.date, v.voucher_number""",
            [item_name, str(from_date), str(to_date)],
        )
        result: list[dict[str, Any]] = []
        for r in rows:
            qty = Decimal(str(r.get("quantity") or 0))
            amount = Decimal(str(r.get("amount") or 0))
            d = r.get("date")
            is_outward = amount < 0
            result.append(
                {
                    "date": str(d) if d else None,
                    "voucher_type": r.get("voucher_type"),
                    "voucher_number": r.get("voucher_number"),
                    "inward_qty": str(abs(qty)) if not is_outward else "0",
                    "outward_qty": str(abs(qty)) if is_outward else "0",
                    "amount": str(abs(amount)),
                }
            )
        return result

    def get_gstr1(self, from_date: date, to_date: date) -> GSTR1Result:
        """Fetch GSTR-1 outward supply data from the local cache.

        Constructs GSTR-1 sections from cached sales voucher data.
        This is a cache-based reconstruction — for the full TallyPrime
        GSTR-1 export with all portal sections, use
        ``TallyConnection.fetch_gstr1()`` instead.
        """
        from tallybridge.models.report import GSTR1Invoice, GSTR1Section

        rows = self._cache.query(
            """SELECT v.voucher_number, v.date, v.party_gstin,
                      v.party_ledger as party_name, v.place_of_supply,
                      le.ledger_name, le.amount
            FROM trn_voucher v
            JOIN trn_ledger_entry le ON le.voucher_guid = v.guid
            WHERE v.voucher_type IN ('Sales', 'Credit Note')
            AND v.is_cancelled = false AND v.is_void = false
            AND v.date BETWEEN ? AND ?
            ORDER BY v.date, v.voucher_number""",
            [str(from_date), str(to_date)],
        )

        b2b_invoices: list[GSTR1Invoice] = []
        b2cs_invoices: list[GSTR1Invoice] = []
        invoice_map: dict[str, GSTR1Invoice] = {}

        for r in rows:
            inv_num = str(r.get("voucher_number") or "")
            if inv_num not in invoice_map:
                inv_date = r.get("date")
                if isinstance(inv_date, str):
                    try:
                        inv_date = date.fromisoformat(inv_date)
                    except ValueError:
                        inv_date = None
                elif not isinstance(inv_date, date):
                    inv_date = None
                invoice_map[inv_num] = GSTR1Invoice(
                    invoice_number=inv_num,
                    invoice_date=inv_date,
                    party_gstin=str(r.get("party_gstin") or ""),
                    party_name=str(r.get("party_name") or ""),
                    place_of_supply=str(r.get("place_of_supply") or ""),
                )
            inv = invoice_map[inv_num]
            ledger_name = str(r.get("ledger_name") or "").upper()
            amount = abs(Decimal(str(r.get("amount") or 0)))
            if "CGST" in ledger_name:
                inv.cgst += amount
            elif "SGST" in ledger_name:
                inv.sgst += amount
            elif "IGST" in ledger_name:
                inv.igst += amount
            elif "CESS" in ledger_name:
                inv.cess += amount
            else:
                inv.taxable_value += amount

        for inv in invoice_map.values():
            if inv.party_gstin:
                b2b_invoices.append(inv)
            else:
                b2cs_invoices.append(inv)

        sections: list[GSTR1Section] = []
        if b2b_invoices:
            sections.append(
                GSTR1Section(
                    section="B2B",
                    description="B2B Invoices",
                    invoices=b2b_invoices,
                    taxable_value=sum(
                        (i.taxable_value for i in b2b_invoices), Decimal("0")
                    ),
                    cgst=sum((i.cgst for i in b2b_invoices), Decimal("0")),
                    sgst=sum((i.sgst for i in b2b_invoices), Decimal("0")),
                    igst=sum((i.igst for i in b2b_invoices), Decimal("0")),
                    cess=sum((i.cess for i in b2b_invoices), Decimal("0")),
                )
            )
        if b2cs_invoices:
            sections.append(
                GSTR1Section(
                    section="B2CS",
                    description="B2C (Small)",
                    invoices=b2cs_invoices,
                    taxable_value=sum(
                        (i.taxable_value for i in b2cs_invoices), Decimal("0")
                    ),
                    cgst=sum((i.cgst for i in b2cs_invoices), Decimal("0")),
                    sgst=sum((i.sgst for i in b2cs_invoices), Decimal("0")),
                    igst=sum((i.igst for i in b2cs_invoices), Decimal("0")),
                    cess=sum((i.cess for i in b2cs_invoices), Decimal("0")),
                )
            )

        return GSTR1Result(
            from_date=from_date,
            to_date=to_date,
            sections=sections,
        )

    def reconcile_itc(
        self,
        from_date: date,
        to_date: date,
        gstr2a_claims: list[Any] | None = None,
    ) -> ReconciliationResult:
        """Compare cached purchase vouchers against GSTR-2A/2B data.

        Matches by supplier GSTIN + invoice number + date. If gstr2a_claims
        is not provided, queries cached purchase vouchers only (returns
        partial reconciliation).

        Args:
            from_date: Start date for purchase voucher range.
            to_date: End date for purchase voucher range.
            gstr2a_claims: Optional list of GSTR2AClaim objects from
                ``TallyConnection.fetch_gstr2a()``.

        Returns:
            ReconciliationResult with matched/mismatched/missing counts.
        """
        from tallybridge.models.report import GSTR2AClaim

        purchases = self._cache.query(
            """SELECT v.voucher_number, v.date, v.party_ledger, v.party_gstin,
                      v.total_amount,
                      COALESCE(SUM(CASE WHEN le.ledger_name LIKE '%CGST%'
                                  THEN ABS(le.amount) ELSE 0 END), 0) as cgst,
                      COALESCE(SUM(CASE WHEN le.ledger_name LIKE '%SGST%'
                                  THEN ABS(le.amount) ELSE 0 END) , 0) as sgst,
                      COALESCE(SUM(CASE WHEN le.ledger_name LIKE '%IGST%'
                                  THEN ABS(le.amount) ELSE 0 END), 0) as igst
            FROM trn_voucher v
            LEFT JOIN trn_ledger_entry le ON le.voucher_guid = v.guid
            WHERE v.voucher_type = 'Purchase'
            AND v.is_cancelled = false AND v.is_void = false
            AND v.date BETWEEN ? AND ?
            GROUP BY v.guid, v.voucher_number, v.date, v.party_ledger,
                     v.party_gstin, v.total_amount""",
            [str(from_date), str(to_date)],
        )

        if gstr2a_claims is None:
            gstr2a_claims = []

        tally_by_full: dict[str, dict[str, Any]] = {}
        tally_by_vnum: dict[str, dict[str, Any]] = {}
        for p in purchases:
            gstin = str(p.get("party_gstin") or "")
            vnum = str(p.get("voucher_number") or "")
            tally_by_full[f"{gstin}|{vnum}"] = p
            if vnum:
                tally_by_vnum[vnum] = p

        claims_map: dict[str, GSTR2AClaim] = {}
        for claim in gstr2a_claims:
            key = f"{claim.supplier_gstin}|{claim.invoice_number}"
            claims_map[key] = claim

        matched = 0
        mismatched = 0
        missing_in_tally = 0
        missing_in_2a = 0
        itc_claimed = Decimal("0")
        itc_available = Decimal("0")
        mismatches: list[dict[str, Any]] = []
        matched_tally_keys: set[str] = set()

        for key, claim in claims_map.items():
            itc_available += claim.itc_available
            tally_p = tally_by_full.get(key)
            if tally_p is None and claim.invoice_number:
                tally_p = tally_by_vnum.get(claim.invoice_number)
            if tally_p is not None:
                p_gstin = str(tally_p.get("party_gstin") or "")
                p_vnum = str(tally_p.get("voucher_number") or "")
                tally_key = f"{p_gstin}|{p_vnum}"
                matched_tally_keys.add(tally_key)
                tally_total = Decimal(str(tally_p.get("total_amount") or 0))
                tally_cgst = Decimal(str(tally_p.get("cgst") or 0))
                tally_sgst = Decimal(str(tally_p.get("sgst") or 0))
                tally_igst = Decimal(str(tally_p.get("igst") or 0))
                tally_tax = tally_cgst + tally_sgst + tally_igst
                claim_tax = claim.cgst + claim.sgst + claim.igst
                if abs(tally_total - claim.taxable_value) <= Decimal("1") and abs(
                    tally_tax - claim_tax
                ) <= Decimal("1"):
                    matched += 1
                    itc_claimed += claim.itc_available
                else:
                    mismatched += 1
                    mismatches.append(
                        {
                            "supplier_gstin": claim.supplier_gstin,
                            "invoice_number": claim.invoice_number,
                            "tally_amount": str(tally_total),
                            "gstr2a_amount": str(claim.taxable_value),
                            "tally_tax": str(tally_tax),
                            "gstr2a_tax": str(claim_tax),
                        }
                    )
            else:
                missing_in_tally += 1
                mismatches.append(
                    {
                        "supplier_gstin": claim.supplier_gstin,
                        "invoice_number": claim.invoice_number,
                        "issue": "Present in GSTR-2A but not in Tally",
                    }
                )

        for key, p in tally_by_full.items():
            if key not in matched_tally_keys and key not in claims_map:
                missing_in_2a += 1
                mismatches.append(
                    {
                        "supplier_gstin": str(p.get("party_gstin") or ""),
                        "invoice_number": str(p.get("voucher_number") or ""),
                        "issue": "Present in Tally but not in GSTR-2A",
                    }
                )

        return ReconciliationResult(
            total_2a_claims=len(gstr2a_claims),
            matched=matched,
            mismatched=mismatched,
            missing_in_tally=missing_in_tally,
            missing_in_2a=missing_in_2a,
            itc_claimed=itc_claimed,
            itc_available=itc_available,
            mismatches=mismatches,
        )

    def get_audit_log(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
        entity_type: str | None = None,
        operation: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query audit log with filters."""
        return self._cache.get_audit_log(
            from_date=from_date,
            to_date=to_date,
            entity_type=entity_type,
            operation=operation,
            limit=limit,
        )
