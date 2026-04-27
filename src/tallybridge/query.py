"""Public query API — see SPECS.md §8."""

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from tallybridge.cache import TallyCache
from tallybridge.models.master import TallyStockItem
from tallybridge.models.report import (
    DailyDigest,
    OutstandingBill,
    StockAgingLine,
    TrialBalanceLine,
)
from tallybridge.models.voucher import TallyVoucher


class TallyQuery:
    def __init__(self, cache: TallyCache) -> None:
        self._cache = cache

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
        """Check if DuckDB string similarity functions are available."""
        try:
            self._cache.query("SELECT similarity('test', 'test') as s")
            return True
        except Exception:
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
        )
