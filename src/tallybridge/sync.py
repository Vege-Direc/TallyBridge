"""AlterID-based sync engine — see SPECS.md §7."""

import asyncio
import time
from typing import Literal

from loguru import logger

from tallybridge.cache import TallyCache
from tallybridge.connection import TallyConnection
from tallybridge.exceptions import TallyConnectionError, TallyDataError
from tallybridge.models.report import SyncResult
from tallybridge.parser import TallyXMLParser

ENTITY_CONFIG: dict[str, dict] = {
    "group": {
        "tally_type": "Group",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT", "PRIMARYGROUP",
                    "ISREVENUE", "AFFECTSGROSSPROFIT", "NETDEBITCREDIT"],
    },
    "ledger": {
        "tally_type": "Ledger",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT", "OPENINGBALANCE",
                    "CLOSINGBALANCE", "ISREVENUE", "AFFECTSGROSSPROFIT",
                    "GSTIN", "LEDMAILINGNAME"],
    },
    "voucher_type": {
        "tally_type": "VoucherType",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT"],
    },
    "unit": {
        "tally_type": "Unit",
        "fields": ["NAME", "GUID", "ALTERID", "UNITTYPE", "BASEUNITS",
                    "DECIMALPLACES", "SYMBOL"],
    },
    "stock_group": {
        "tally_type": "StockGroup",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT", "SHOULDQUANTITIESADD"],
    },
    "stock_item": {
        "tally_type": "StockItem",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT", "BASEUNITS",
                    "GSTRATE", "HSNCODE", "OPENINGBALANCE", "CLOSINGBALANCE"],
    },
    "cost_center": {
        "tally_type": "CostCentre",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT", "EMAIL",
                    "COSTCENTRETYPE"],
    },
    "voucher": {
        "tally_type": "Voucher",
        "fields": ["GUID", "ALTERID", "DATE", "EFFECTIVEDATE", "VOUCHERNUMBER",
                    "VOUCHERTYPENAME", "REFERENCE", "NARRATION",
                    "PARTYLEDGERNAME", "PARTYMAILINGNAME", "PLACEOFSUPPLY",
                    "BASICDUEDATEOFPYMT", "ENTEREDBY",
                    "ISCANCELLED", "ISOPTIONAL", "ISPOSTDATED", "ISVOID",
                    "LEDGERENTRIES", "INVENTORYENTRIES"],
    },
}

SYNC_ORDER: list[str] = [
    "group", "ledger", "voucher_type",
    "unit", "stock_group", "stock_item",
    "cost_center", "voucher",
]
VOUCHER_BATCH_SIZE = 1000


class TallySyncEngine:
    def __init__(
        self,
        connection: TallyConnection,
        cache: TallyCache,
        parser: TallyXMLParser,
    ) -> None:
        self._connection = connection
        self._cache = cache
        self._parser = parser
        self._lock = asyncio.Lock()

    async def sync_entity(
        self,
        entity_type: Literal[
            "ledger", "group", "stock_item", "voucher_type", "voucher",
            "unit", "stock_group", "cost_center",
        ],
    ) -> SyncResult:
        """Sync one entity. Returns SyncResult — NEVER raises."""
        start = time.monotonic()
        config = ENTITY_CONFIG.get(entity_type)
        if config is None:
            return SyncResult(
                entity_type=entity_type,
                success=False,
                error_message=f"Unknown entity type: {entity_type}",
            )

        try:
            last_alter_id = self._cache.get_last_alter_id(entity_type)
            max_alter_id = await self._connection.get_alter_id_max(config["tally_type"])

            if max_alter_id <= last_alter_id:
                return SyncResult(
                    entity_type=entity_type,
                    alter_id_before=last_alter_id,
                    alter_id_after=last_alter_id,
                    duration_seconds=time.monotonic() - start,
                )

            filter_expr = f"$ALTERID > {last_alter_id}" if last_alter_id > 0 else None
            xml = await self._connection.export_collection(
                f"Sync_{entity_type}",
                config["tally_type"],
                config["fields"],
                filter_expr=filter_expr,
            )

            records = self._parse_entity(entity_type, xml)
            count = self._upsert_entity(entity_type, records)

            new_alter_id = max_alter_id
            self._cache.update_sync_state(entity_type, new_alter_id, count)

            return SyncResult(
                entity_type=entity_type,
                records_synced=count,
                alter_id_before=last_alter_id,
                alter_id_after=new_alter_id,
                duration_seconds=time.monotonic() - start,
            )
        except (TallyConnectionError, TallyDataError) as exc:
            logger.warning("Sync failed for {}: {}", entity_type, exc)
            return SyncResult(
                entity_type=entity_type,
                success=False,
                error_message=str(exc),
                duration_seconds=time.monotonic() - start,
            )
        except Exception as exc:
            logger.warning("Unexpected sync error for {}: {}", entity_type, exc)
            return SyncResult(
                entity_type=entity_type,
                success=False,
                error_message=str(exc),
                duration_seconds=time.monotonic() - start,
            )

    async def sync_all(self) -> dict[str, SyncResult]:
        """Sync all entities in SYNC_ORDER. Holds _lock for the full cycle."""
        async with self._lock:
            results: dict[str, SyncResult] = {}
            for entity_type in SYNC_ORDER:
                results[entity_type] = await self.sync_entity(entity_type)
            return results

    async def full_sync(self) -> dict[str, SyncResult]:
        """Reset all AlterIDs to 0 in sync_state, then run sync_all()."""
        for entity_type in SYNC_ORDER:
            self._cache.update_sync_state(entity_type, 0, 0)
        return await self.sync_all()

    async def run_continuous(self, frequency_minutes: int = 5) -> None:
        """Run sync_all() every frequency_minutes using asyncio.sleep()."""
        while True:
            try:
                await self.sync_all()
            except Exception as exc:
                logger.warning("Continuous sync error: {}", exc)
            await asyncio.sleep(frequency_minutes * 60)

    async def is_tally_available(self) -> bool:
        """Non-blocking Tally ping."""
        return await self._connection.ping()

    def _parse_entity(self, entity_type: str, xml: str) -> list:
        parse_map = {
            "ledger": self._parser.parse_ledgers,
            "group": self._parser.parse_groups,
            "stock_item": self._parser.parse_stock_items,
            "voucher_type": self._parser.parse_voucher_types,
            "unit": self._parser.parse_units,
            "stock_group": self._parser.parse_stock_groups,
            "cost_center": self._parser.parse_cost_centers,
            "voucher": self._parser.parse_vouchers,
        }
        parse_fn = parse_map.get(entity_type)
        if parse_fn is None:
            return []
        return parse_fn(xml)

    def _upsert_entity(self, entity_type: str, records: list) -> int:
        upsert_map = {
            "ledger": self._cache.upsert_ledgers,
            "group": self._cache.upsert_groups,
            "stock_item": self._cache.upsert_stock_items,
            "voucher_type": self._cache.upsert_voucher_types,
            "unit": self._cache.upsert_units,
            "stock_group": self._cache.upsert_stock_groups,
            "cost_center": self._cache.upsert_cost_centers,
            "voucher": self._cache.upsert_vouchers,
        }
        upsert_fn = upsert_map.get(entity_type)
        if upsert_fn is None:
            return 0
        return upsert_fn(records)
