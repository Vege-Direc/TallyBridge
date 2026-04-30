"""Unified TallyBridge client — sync, query, and write-back in one object.

See SPECS.md §28.
"""

from __future__ import annotations

from typing import Any

from tallybridge.cache import TallyCache
from tallybridge.config import TallyBridgeConfig
from tallybridge.connection import TallyConnection
from tallybridge.models.report import ImportResult, SyncResult
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
        self._cache = TallyCache(self._config.db_path)
        self._cache.initialize()
        self._connection = TallyConnection(self._config)
        self._parser = TallyXMLParser()
        self._sync_engine = TallySyncEngine(
            self._connection, self._cache, self._parser
        )
        self._query = TallyQuery(self._cache)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._query, name)

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
    ) -> ImportResult:
        """Create a ledger in TallyPrime.

        Requires ``TALLYBRIDGE_ALLOW_WRITES=true``.

        Args:
            name: Ledger name.
            parent_group: Parent group name.
            opening_balance: Opening balance string (e.g. ``"5000"``).

        Returns:
            ImportResult with created/altered/deleted/error counts.
        """
        xml_data = TallyConnection.build_ledger_xml(
            name=name,
            parent_group=parent_group,
            opening_balance=opening_balance,
        )
        return await self._connection.import_masters(xml_data)

    async def create_voucher(
        self,
        voucher_type: str,
        date: str,
        ledger_entries: list[dict[str, str]],
        narration: str | None = None,
        voucher_number: str | None = None,
        party_ledger: str | None = None,
    ) -> ImportResult:
        """Create a voucher in TallyPrime.

        Requires ``TALLYBRIDGE_ALLOW_WRITES=true``.

        Args:
            voucher_type: Voucher type name (e.g. ``"Sales"``, ``"Payment"``).
            date: Date in YYYYMMDD format.
            ledger_entries: List of dicts with keys ``"ledger_name"`` and
                ``"amount"`` (positive=Dr, negative=Cr).
            narration: Optional narration text.
            voucher_number: Optional voucher number.
            party_ledger: Optional party ledger name.

        Returns:
            ImportResult with created/altered/deleted/error counts.
        """
        xml_data = TallyConnection.build_voucher_xml(
            voucher_type=voucher_type,
            date=date,
            ledger_entries=ledger_entries,
            narration=narration,
            voucher_number=voucher_number,
            party_ledger=party_ledger,
        )
        return await self._connection.import_vouchers(xml_data)

    async def cancel_voucher(
        self, guid: str, voucher_type: str = "Sales"
    ) -> ImportResult:
        """Cancel a voucher in TallyPrime.

        Requires ``TALLYBRIDGE_ALLOW_WRITES=true``.

        Args:
            guid: Voucher GUID to cancel.
            voucher_type: Voucher type name (default ``"Sales"``).

        Returns:
            ImportResult with created/altered/deleted/error counts.
        """
        xml_data = TallyConnection.build_cancel_voucher_xml(
            guid=guid, voucher_type=voucher_type
        )
        return await self._connection.import_vouchers(xml_data)

    async def close(self) -> None:
        """Close connections and release resources."""
        await self._connection.close()
        self._cache.close()

    async def __aenter__(self) -> TallyBridge:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
