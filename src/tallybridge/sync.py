"""AlterID-based sync engine — see SPECS.md §7."""

import asyncio
import time
from typing import Any

from loguru import logger

from tallybridge.cache import TallyCache
from tallybridge.connection import TallyConnection
from tallybridge.exceptions import TallyConnectionError, TallyDataError
from tallybridge.models.report import SyncResult
from tallybridge.parser import TallyXMLParser
from tallybridge.version import TallyProduct, detect_tally_version

ENTITY_CONFIG: dict[str, dict[str, Any]] = {
    "group": {
        "tally_type": "Group",
        "fields": [
            "NAME",
            "GUID",
            "ALTERID",
            "PARENT",
            "PRIMARYGROUP",
            "ISREVENUE",
            "AFFECTSGROSSPROFIT",
            "NETDEBITCREDIT",
        ],
    },
    "ledger": {
        "tally_type": "Ledger",
        "fields": [
            "NAME",
            "GUID",
            "ALTERID",
            "PARENT",
            "OPENINGBALANCE",
            "CLOSINGBALANCE",
            "ISREVENUE",
            "AFFECTSGROSSPROFIT",
            "GSTIN",
            "LEDMAILINGNAME",
        ],
    },
    "voucher_type": {
        "tally_type": "VoucherType",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT"],
    },
    "unit": {
        "tally_type": "Unit",
        "fields": [
            "NAME",
            "GUID",
            "ALTERID",
            "UNITTYPE",
            "BASEUNITS",
            "DECIMALPLACES",
            "SYMBOL",
        ],
    },
    "stock_group": {
        "tally_type": "StockGroup",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT", "SHOULDQUANTITIESADD"],
    },
    "stock_item": {
        "tally_type": "StockItem",
        "fields": [
            "NAME",
            "GUID",
            "ALTERID",
            "PARENT",
            "BASEUNITS",
            "GSTRATE",
            "HSNCODE",
            "OPENINGBALANCE",
            "CLOSINGBALANCE",
        ],
    },
    "cost_center": {
        "tally_type": "CostCentre",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT", "EMAIL", "COSTCENTRETYPE"],
    },
    "voucher": {
        "tally_type": "Voucher",
        # NOTE: LEDGERENTRIES and INVENTORYENTRIES are TDL collection references,
        # not scalar fields. Including them in <FETCH> causes errors or empty
        # responses in some Tally versions. Sub-collections (LEDGERENTRIES.LIST,
        # ALLLEDGERENTRIES.LIST, INVENTORYENTRIES.LIST) are automatically included
        # in the XML response by Tally and parsed by TallyXMLParser.
        "fields": [
            "GUID",
            "ALTERID",
            "DATE",
            "EFFECTIVEDATE",
            "VOUCHERNUMBER",
            "VOUCHERTYPENAME",
            "REFERENCE",
            "NARRATION",
            "PARTYLEDGERNAME",
            "PARTYMAILINGNAME",
            "PLACEOFSUPPLY",
            "BASICDUEDATEOFPYMT",
            "ENTEREDBY",
            "ISCANCELLED",
            "ISOPTIONAL",
            "ISPOSTDATED",
            "ISVOID",
        ],
    },
}

SYNC_ORDER: list[str] = [
    "group",
    "ledger",
    "voucher_type",
    "unit",
    "stock_group",
    "stock_item",
    "cost_center",
    "voucher",
]
VOUCHER_BATCH_SIZE = 5000


class TallySyncEngine:
    def __init__(
        self,
        connection: TallyConnection,
        cache: TallyCache,
        parser: TallyXMLParser,
        company: str | None = None,
    ) -> None:
        self._connection = connection
        self._cache = cache
        self._parser = parser
        self._lock = asyncio.Lock()
        self._company = company
        self._detected_version: TallyProduct | None = None

    async def sync_entity(self, entity_type: str) -> SyncResult:
        """Sync one entity. Returns SyncResult — NEVER raises.

        For vouchers, uses batched fetching via AlterID ranges to avoid
        hanging Tally with large result sets (batch size = 5000, max 10000).
        """
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
            max_alter_id = await self._connection.get_alter_id_max(
                config["tally_type"], company=self._company
            )

            if max_alter_id <= last_alter_id:
                return SyncResult(
                    entity_type=entity_type,
                    alter_id_before=last_alter_id,
                    alter_id_after=last_alter_id,
                    duration_seconds=time.monotonic() - start,
                )

            if entity_type == "voucher":
                total_count = await self._sync_vouchers_batched(
                    last_alter_id, max_alter_id
                )
            else:
                filter_expr = (
                    f"$ALTERID > {last_alter_id}" if last_alter_id > 0 else None
                )
                xml = await self._connection.export_collection(
                    f"Sync_{entity_type}",
                    config["tally_type"],
                    config["fields"],
                    filter_expr=filter_expr,
                    company=self._company,
                )
                records = self._parse_entity(entity_type, xml)
                total_count = self._upsert_entity(entity_type, records, self._company)

            self._cache.update_sync_state(entity_type, max_alter_id, total_count)

            return SyncResult(
                entity_type=entity_type,
                records_synced=total_count,
                alter_id_before=last_alter_id,
                alter_id_after=max_alter_id,
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

    async def _sync_vouchers_batched(
        self, last_alter_id: int, max_alter_id: int
    ) -> int:
        """Fetch vouchers in batches of VOUCHER_BATCH_SIZE using AlterID ranges.

        Per tally-database-loader reference: batch size 5000 is stable,
        do not exceed 10000 or Tally may hang indefinitely.
        """
        voucher_config = ENTITY_CONFIG["voucher"]
        total_count = 0
        batch_start = last_alter_id

        while True:
            batch_end = batch_start + VOUCHER_BATCH_SIZE
            filter_expr = f"$ALTERID > {batch_start} AND $ALTERID <= {batch_end}"

            xml = await self._connection.export_collection(
                f"Sync_voucher_{batch_start}",
                voucher_config["tally_type"],
                voucher_config["fields"],
                filter_expr=filter_expr,
                company=self._company,
            )

            records = self._parse_entity("voucher", xml)
            if not records:
                break

            count = self._upsert_entity("voucher", records, self._company)
            total_count += count
            batch_start = batch_end

            logger.info(
                "Voucher batch: AlterID {}-{}, {} records, total {}",
                batch_start,
                batch_end,
                count,
                total_count,
            )

            if batch_end >= max_alter_id:
                break

        return total_count

    async def sync_all(self) -> dict[str, SyncResult]:
        """Sync all entities in SYNC_ORDER. Holds _lock for the full cycle.

        On first sync, detects the Tally product version for compatibility.
        """
        async with self._lock:
            if self._detected_version is None:
                try:
                    self._detected_version = await detect_tally_version(
                        self._connection
                    )
                    logger.info(
                        "Tally version detected: {}",
                        self._detected_version.display_name,
                    )
                except Exception:
                    self._detected_version = TallyProduct.ERP9
                    logger.warning(
                        "Version detection failed; assuming Tally.ERP 9"
                    )
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

    async def get_active_company(self) -> str | None:
        """Return the active company name from Tally, or None if not set.

        If self._company is already set, return it. Otherwise, query Tally
        for the list of open companies and return the first one.
        """
        if self._company:
            return self._company
        try:
            companies = await self._connection.get_company_list()
            return companies[0] if companies else None
        except Exception:
            return None

    def _parse_entity(self, entity_type: str, xml: str) -> list[Any]:
        parse_map: dict[str, Any] = {
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
        result: list[Any] = parse_fn(xml)
        return result

    def _upsert_entity(
        self, entity_type: str, records: list[Any], company: str | None = None
    ) -> int:
        upsert_map: dict[str, Any] = {
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
        if entity_type == "voucher":
            count: int = upsert_fn(records, company=company)
        else:
            count = upsert_fn(records)
        return count
