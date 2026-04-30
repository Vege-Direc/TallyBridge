"""Unified TallyBridge client — sync, query, and write-back in one object.

See SPECS.md §28, §29.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Any

from tallybridge.cache import TallyCache
from tallybridge.config import TallyBridgeConfig
from tallybridge.connection import TallyConnection
from tallybridge.exceptions import TallyDataError
from tallybridge.models.report import ImportResult, SyncResult, ValidationResult
from tallybridge.parser import TallyXMLParser
from tallybridge.query import TallyQuery
from tallybridge.sync import TallySyncEngine


class TallyBridge:
    """Unified TallyPrime client — sync, query, and write-back in one object.

    Usage::

        import tallybridge
        tb = tallybridge.connect()

        # Read (existing TallyQuery methods)
        digest = tb.get_daily_digest()
        balance = tb.get_ledger_balance("Cash")

        # Write (requires TALLYBRIDGE_ALLOW_WRITES=true)
        result = await tb.create_ledger("New Customer", "Sundry Debtors")
        result = await tb.create_voucher("Sales", "20250101", entries)
        await tb.cancel_voucher("guid-abc-123")

        # Or as async context manager
        async with tallybridge.TallyBridge() as tb:
            await tb.sync()
    """

    def __init__(self, config: TallyBridgeConfig | None = None) -> None:
        self._config = config or TallyBridgeConfig()
        self._cache = TallyCache(
            self._config.db_path,
            cache_ttl=float(self._config.query_cache_ttl),
            slow_threshold=self._config.slow_query_threshold,
        )
        self._cache.initialize()
        self._connection = TallyConnection(self._config)
        self._parser = TallyXMLParser()
        self._sync_engine = TallySyncEngine(self._connection, self._cache, self._parser)
        self._query = TallyQuery(self._cache)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._query, name)

    async def validate_voucher(
        self,
        voucher_type: str,
        date_str: str,
        ledger_entries: list[dict[str, str]],
        party_ledger: str | None = None,
        voucher_number: str | None = None,
    ) -> ValidationResult:
        """Validate a voucher before posting to TallyPrime.

        Checks performed:
        1. All referenced ledgers exist in cache
        2. Debit total equals credit total (balanced voucher)
        3. Party ledger belongs to Sundry Debtors/Creditors group
        4. Voucher type exists in cache
        5. Date is valid and within allowed range
        6. No duplicate voucher number (if provided)

        Args:
            voucher_type: Voucher type name (e.g. ``"Sales"``, ``"Payment"``).
            date_str: Date in YYYYMMDD format.
            ledger_entries: List of dicts with keys ``"ledger_name"`` and
                ``"amount"`` (positive=Dr, negative=Cr).
            party_ledger: Optional party ledger name.
            voucher_number: Optional voucher number to check for duplicates.

        Returns:
            ValidationResult with valid=True/False and error/warning lists.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not voucher_type.strip():
            errors.append("Voucher type is empty")
        else:
            vtype_rows = self._cache.query(
                "SELECT name FROM mst_voucher_type WHERE name = ?",
                [voucher_type],
            )
            if not vtype_rows:
                errors.append(f"Voucher type '{voucher_type}' not found in cache")

        if not date_str or not re.match(r"^\d{8}$", date_str):
            errors.append(f"Invalid date format '{date_str}', expected YYYYMMDD")
        else:
            try:
                parsed = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
                if parsed.year < 2000 or parsed.year > 2100:
                    errors.append(
                        f"Date {date_str} is outside allowed range (2000-2100)"
                    )
            except ValueError:
                errors.append(f"Invalid date '{date_str}'")

        for entry in ledger_entries:
            ledger_name = entry.get("ledger_name", "")
            if not ledger_name:
                errors.append("Ledger entry has empty ledger_name")
                continue
            lrows = self._cache.query(
                "SELECT name FROM mst_ledger WHERE name = ?",
                [ledger_name],
            )
            if not lrows:
                errors.append(f"Ledger '{ledger_name}' not found in cache")

        debit_total = Decimal("0")
        credit_total = Decimal("0")
        for entry in ledger_entries:
            try:
                amount = Decimal(str(entry.get("amount", "0")))
            except Exception:
                errors.append(
                    f"Invalid amount '{entry.get('amount')}' for ledger "
                    f"'{entry.get('ledger_name', '')}'"
                )
                continue
            if amount > 0:
                debit_total += amount
            elif amount < 0:
                credit_total += abs(amount)
        if debit_total != credit_total:
            errors.append(
                f"Unbalanced voucher: debit={debit_total}, credit={credit_total}"
            )

        if party_ledger:
            prows = self._cache.query(
                "SELECT parent_group FROM mst_ledger WHERE name = ?",
                [party_ledger],
            )
            if prows:
                pg = prows[0]["parent_group"] or ""
                if pg not in ("Sundry Debtors", "Sundry Creditors"):
                    warnings.append(
                        f"Party ledger '{party_ledger}' is in group '{pg}', "
                        f"expected 'Sundry Debtors' or 'Sundry Creditors'"
                    )
            else:
                errors.append(f"Party ledger '{party_ledger}' not found in cache")

        if voucher_number:
            drows = self._cache.query(
                "SELECT guid FROM trn_voucher WHERE voucher_number = ? "
                "AND is_cancelled = false",
                [voucher_number],
            )
            if drows:
                errors.append(
                    f"Duplicate voucher number '{voucher_number}' already exists"
                )

        return ValidationResult(
            valid=len(errors) == 0, errors=errors, warnings=warnings
        )

    async def validate_ledger(
        self,
        name: str,
        parent_group: str,
    ) -> ValidationResult:
        """Validate a ledger before creating in TallyPrime.

        Checks:
        1. Ledger name doesn't already exist in cache
        2. Parent group exists in cache
        3. Name is not empty or whitespace

        Args:
            name: Ledger name.
            parent_group: Parent group name.

        Returns:
            ValidationResult with valid=True/False and error/warning lists.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not name or not name.strip():
            errors.append("Ledger name is empty or whitespace")

        if name and name.strip():
            lrows = self._cache.query(
                "SELECT name FROM mst_ledger WHERE name = ?",
                [name.strip()],
            )
            if lrows:
                errors.append(f"Ledger '{name}' already exists in cache")

        grows = self._cache.query(
            "SELECT name FROM mst_group WHERE name = ?",
            [parent_group],
        )
        if not grows:
            errors.append(f"Parent group '{parent_group}' not found in cache")

        return ValidationResult(
            valid=len(errors) == 0, errors=errors, warnings=warnings
        )

    async def sync(self, full: bool = False) -> dict[str, SyncResult]:
        """Sync data from TallyPrime.

        Args:
            full: If True, force a full re-sync (resets AlterIDs to 0 first).
        """
        if full:
            return await self._sync_engine.full_sync()
        return await self._sync_engine.sync_all()

    async def create_ledger(
        self,
        name: str,
        parent_group: str = "Sundry Debtors",
        opening_balance: str = "0",
        validate: bool = True,
    ) -> ImportResult:
        if validate:
            result = await self.validate_ledger(name, parent_group)
            if not result.valid:
                self._cache.log_audit(
                    operation="create",
                    entity_type="ledger",
                    entity_name=name,
                    success=False,
                    details={"errors": result.errors},
                )
                raise TallyDataError(
                    f"Ledger validation failed: {'; '.join(result.errors)}"
                )
        xml_data = TallyConnection.build_ledger_xml(
            name=name,
            parent_group=parent_group,
            opening_balance=opening_balance,
        )
        import_result = await self._connection.import_masters(xml_data)
        self._cache.log_audit(
            operation="create",
            entity_type="ledger",
            entity_name=name,
            success=import_result.created > 0 or import_result.altered > 0,
            details={"parent_group": parent_group, "opening_balance": opening_balance},
        )
        return import_result

    async def create_voucher(
        self,
        voucher_type: str,
        date: str,
        ledger_entries: list[dict[str, str]],
        narration: str | None = None,
        voucher_number: str | None = None,
        party_ledger: str | None = None,
        validate: bool = True,
    ) -> ImportResult:
        if validate:
            result = await self.validate_voucher(
                voucher_type=voucher_type,
                date_str=date,
                ledger_entries=ledger_entries,
                party_ledger=party_ledger,
                voucher_number=voucher_number,
            )
            if not result.valid:
                self._cache.log_audit(
                    operation="create",
                    entity_type="voucher",
                    entity_name=voucher_number,
                    success=False,
                    details={"errors": result.errors, "voucher_type": voucher_type},
                )
                raise TallyDataError(
                    f"Voucher validation failed: {'; '.join(result.errors)}"
                )
        xml_data = TallyConnection.build_voucher_xml(
            voucher_type=voucher_type,
            date=date,
            ledger_entries=ledger_entries,
            narration=narration,
            voucher_number=voucher_number,
            party_ledger=party_ledger,
        )
        import_result = await self._connection.import_vouchers(xml_data)
        self._cache.log_audit(
            operation="create",
            entity_type="voucher",
            entity_name=voucher_number,
            success=import_result.created > 0 or import_result.altered > 0,
            details={
                "voucher_type": voucher_type,
                "date": date,
                "entries_count": len(ledger_entries),
            },
        )
        return import_result

    async def cancel_voucher(
        self, guid: str, voucher_type: str = "Sales"
    ) -> ImportResult:
        xml_data = TallyConnection.build_cancel_voucher_xml(
            guid=guid, voucher_type=voucher_type
        )
        import_result = await self._connection.import_vouchers(xml_data)
        self._cache.log_audit(
            operation="cancel",
            entity_type="voucher",
            entity_guid=guid,
            success=import_result.altered > 0,
            details={"voucher_type": voucher_type},
        )
        return import_result

    async def close(self) -> None:
        """Close connections and release resources."""
        await self._connection.close()
        self._cache.close()

    async def __aenter__(self) -> TallyBridge:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
