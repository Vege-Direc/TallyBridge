"""AlterID-based sync engine — see SPECS.md §7."""

import asyncio
import time
from typing import Any

from loguru import logger

from tallybridge.cache import TallyCache
from tallybridge.config import get_config
from tallybridge.connection import TallyConnection
from tallybridge.exceptions import TallyConnectionError, TallyDataError
from tallybridge.models.report import SyncResult
from tallybridge.parser import TallyXMLParser
from tallybridge.version import TallyProduct

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
    "godown": {
        "tally_type": "Godown",
        "fields": ["NAME", "GUID", "ALTERID", "PARENT"],
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
    "godown",
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
        voucher_batch_size: int | None = None,
    ) -> None:
        self._connection = connection
        self._cache = cache
        self._parser = parser
        self._lock = asyncio.Lock()
        self._company = company
        self._detected_version: TallyProduct | None = None
        self._shutdown_event = asyncio.Event()
        if voucher_batch_size is not None:
            self._voucher_batch_size = voucher_batch_size
        else:
            try:
                self._voucher_batch_size = get_config().voucher_batch_size
            except Exception:
                self._voucher_batch_size = VOUCHER_BATCH_SIZE

    async def sync_entity(self, entity_type: str) -> SyncResult:
        """Sync one entity. Returns SyncResult — NEVER raises.

        For vouchers, uses batched fetching via AlterID ranges to avoid
        hanging Tally with large result sets (batch size = 5000, max 10000).
        Always includes SVCURRENTCOMPANY after first company detection.
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
            company = await self._ensure_company()
            last_alter_id = self._cache.get_last_alter_id(entity_type)
            max_alter_id = await self._connection.get_alter_id_max(
                config["tally_type"], company=company
            )

            if max_alter_id <= last_alter_id:
                return SyncResult(
                    entity_type=entity_type,
                    alter_id_before=last_alter_id,
                    alter_id_after=last_alter_id,
                    duration_seconds=time.monotonic() - start,
                )

            if entity_type == "voucher":
                total_count, committed_alter_id = await self._sync_vouchers_batched(
                    last_alter_id, max_alter_id, company
                )
            elif (max_alter_id - last_alter_id) > self._voucher_batch_size:
                total_count, committed_alter_id = await self._sync_master_batched(
                    entity_type, last_alter_id, max_alter_id, company
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
                    company=company,
                )
                records = self._parse_entity(entity_type, xml)
                total_count, committed_alter_id = self._upsert_entity(
                    entity_type, records, company
                )

            safe_alter_id = (
                committed_alter_id if committed_alter_id > 0 else max_alter_id
            )
            self._cache.update_sync_state(entity_type, safe_alter_id, total_count)

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
        self, last_alter_id: int, max_alter_id: int, company: str | None = None
    ) -> tuple[int, int]:
        """Fetch vouchers in batches of VOUCHER_BATCH_SIZE using AlterID ranges.

        Returns (total_count, max_committed_alter_id) so sync_state is only
        advanced to the highest alter_id that was actually committed.
        """
        voucher_config = ENTITY_CONFIG["voucher"]
        total_count = 0
        max_committed_alter_id = 0
        batch_start = last_alter_id

        while True:
            batch_end = batch_start + self._voucher_batch_size
            filter_expr = f"$ALTERID > {batch_start} AND $ALTERID <= {batch_end}"

            xml = await self._connection.export_collection(
                f"Sync_voucher_{batch_start}",
                voucher_config["tally_type"],
                voucher_config["fields"],
                filter_expr=filter_expr,
                company=company,
            )

            records = self._parse_entity("voucher", xml)
            if not records:
                break

            count, batch_max_id = self._upsert_entity("voucher", records, company)
            total_count += count
            if batch_max_id > max_committed_alter_id:
                max_committed_alter_id = batch_max_id
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

        return total_count, max_committed_alter_id

    async def _sync_master_batched(
        self,
        entity_type: str,
        last_alter_id: int,
        max_alter_id: int,
        company: str | None = None,
    ) -> tuple[int, int]:
        """Fetch master entities in batches when alter_id range exceeds threshold.

        Uses the same AlterID-range batching as vouchers but for master entity
        types (ledger, group, stock_item, etc.) that have large record counts.
        """
        config = ENTITY_CONFIG.get(entity_type)
        if config is None:
            return 0, 0

        total_count = 0
        max_committed_alter_id = 0
        batch_start = last_alter_id

        while True:
            batch_end = batch_start + self._voucher_batch_size
            filter_expr = f"$ALTERID > {batch_start} AND $ALTERID <= {batch_end}"

            xml = await self._connection.export_collection(
                f"Sync_{entity_type}_{batch_start}",
                config["tally_type"],
                config["fields"],
                filter_expr=filter_expr,
                company=company,
            )

            records = self._parse_entity(entity_type, xml)
            if not records:
                break

            count, batch_max_id = self._upsert_entity(entity_type, records, company)
            total_count += count
            if batch_max_id > max_committed_alter_id:
                max_committed_alter_id = batch_max_id
            batch_start = batch_end

            logger.info(
                "Master batch {}: AlterID {}-{}, {} records, total {}",
                entity_type,
                batch_start,
                batch_end,
                count,
                total_count,
            )

            if batch_end >= max_alter_id:
                break

        return total_count, max_committed_alter_id

    async def sync_all(self, reconcile: bool = False) -> dict[str, SyncResult]:
        """Sync all entities. Masters are synced concurrently, then vouchers.

        On first sync, detects the Tally product version for compatibility.
        When reconcile=True, compares cache record counts against Tally counts
        after each sync cycle and logs discrepancies.
        """
        async with self._lock:
            if self._detected_version is None:
                try:
                    self._detected_version = await self._connection.detect_version()
                    logger.info(
                        "Tally version detected: {}",
                        self._detected_version.display_name,
                    )
                except Exception:
                    self._detected_version = TallyProduct.ERP9
                    logger.warning("Version detection failed; assuming Tally.ERP 9")

            master_types = [et for et in SYNC_ORDER if et != "voucher"]
            results: dict[str, SyncResult] = {}

            master_coros = [self.sync_entity(et) for et in master_types]
            master_results = await asyncio.gather(*master_coros)
            for entity_type, result in zip(master_types, master_results, strict=True):
                results[entity_type] = result

            results["voucher"] = await self.sync_entity("voucher")

            if reconcile:
                self._reconcile_counts(results)
        return results

    async def detect_deletions(
        self, entity_types: list[str] | None = None
    ) -> dict[str, int]:
        """Detect and delete records that exist in cache but not in Tally.

        Fetches all GUIDs from Tally for each entity type, compares against
        the cached GUIDs, and deletes orphans. Returns a dict mapping
        entity_type to deletion count.

        Args:
            entity_types: Entity types to check. Defaults to SYNC_ORDER minus
                "voucher" (vouchers use ISCANCELLED instead).
        """
        if entity_types is None:
            entity_types = [et for et in SYNC_ORDER if et != "voucher"]

        deletion_counts: dict[str, int] = {}
        company = await self._ensure_company()

        for entity_type in entity_types:
            config = ENTITY_CONFIG.get(entity_type)
            if config is None:
                continue

            try:
                response = await self._connection.export_collection(
                    f"DelCheck_{entity_type}",
                    config["tally_type"],
                    ["GUID"],
                    company=company,
                )
                if isinstance(response, dict):
                    tally_guids = self._extract_guids_json(response)
                else:
                    tally_guids = self._extract_guids(response)
                cached_guids = self._cache.get_cached_guids(entity_type)
                deleted_guids = cached_guids - tally_guids

                if deleted_guids:
                    count = self._cache.delete_records_by_guid(
                        entity_type, deleted_guids
                    )
                    deletion_counts[entity_type] = count
                    logger.warning(
                        "Deleted {} orphaned {} records (GUIDs not in Tally)",
                        count,
                        entity_type,
                    )
                else:
                    deletion_counts[entity_type] = 0
            except Exception as exc:
                logger.warning("Deletion detection failed for {}: {}", entity_type, exc)
                deletion_counts[entity_type] = 0

        return deletion_counts

    @staticmethod
    def _extract_guids(xml: str) -> set[str]:
        """Extract all GUID values from a Tally XML collection response."""
        import xml.etree.ElementTree as ET

        guids: set[str] = set()
        try:
            root = ET.fromstring(xml)
            for elem in root.iter("GUID"):
                if elem.text and elem.text.strip():
                    guids.add(elem.text.strip())
        except ET.ParseError:
            pass
        return guids

    @staticmethod
    def _extract_guids_json(data: dict[str, Any]) -> set[str]:
        """Extract all GUID values from a Tally JSONEx collection response."""
        guids: set[str] = set()
        inner = data.get("data", data)
        messages = inner.get("tallymessage", [])
        if isinstance(messages, dict):
            messages = [messages]
        for msg in messages:
            for _key, obj in msg.items():
                if isinstance(obj, dict):
                    guid = obj.get("guid")
                    if guid and isinstance(guid, str) and guid.strip():
                        guids.add(guid.strip())
        return guids

    def _reconcile_counts(self, results: dict[str, SyncResult]) -> None:
        """Compare cache record counts against Tally counts. Log discrepancies."""
        for entity_type, result in results.items():
            if not result.success:
                continue
            config = ENTITY_CONFIG.get(entity_type)
            if config is None:
                continue
            table_map = {
                "ledger": "mst_ledger",
                "group": "mst_group",
                "stock_item": "mst_stock_item",
                "voucher_type": "mst_voucher_type",
                "unit": "mst_unit",
                "stock_group": "mst_stock_group",
                "cost_center": "mst_cost_center",
                "godown": "mst_godown",
                "voucher": "trn_voucher",
            }
            table = table_map.get(entity_type)
            if table is None:
                continue
            try:
                cache_count = self._cache.conn.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()
                cache_rows = cache_count[0] if cache_count else 0
                if result.records_synced != cache_rows:
                    logger.warning(
                        "Reconciliation mismatch for {}: "
                        "sync reported {} records but cache has {}",
                        entity_type,
                        result.records_synced,
                        cache_rows,
                    )
            except Exception as exc:
                logger.debug("Reconciliation check failed for {}: {}", entity_type, exc)

    async def full_sync(self) -> dict[str, SyncResult]:
        """Reset all AlterIDs to 0 in sync_state, then run sync_all().

        Before re-syncing, takes a content_hash snapshot of all master
        records. After re-sync, compares hashes to detect records that
        changed in Tally since the last sync.
        """
        master_types = [et for et in SYNC_ORDER if et != "voucher"]
        snapshots: dict[str, list[dict[str, Any]]] = {}
        for entity_type in master_types:
            try:
                snapshots[entity_type] = self._cache.detect_content_drift(entity_type)
            except Exception:
                snapshots[entity_type] = []

        for entity_type in SYNC_ORDER:
            self._cache.update_sync_state(entity_type, 0, 0)
        results = await self.sync_all()

        for entity_type in master_types:
            try:
                drift = self._cache.compare_content_drift(
                    entity_type, snapshots[entity_type]
                )
                for d in drift:
                    logger.info(
                        "Drift: {} '{}' ({}) hash changed",
                        entity_type,
                        d["name"],
                        d["guid"],
                    )
            except Exception as exc:
                logger.debug("Drift detection failed for {}: {}", entity_type, exc)

        deletions = await self.detect_deletions(entity_types=master_types)
        total_deleted = sum(deletions.values())
        if total_deleted > 0:
            logger.warning(
                "Full sync completed with {} total deletions: {}",
                total_deleted,
                deletions,
            )

        return results

    async def run_continuous(self, frequency_minutes: int = 5) -> None:
        """Run sync_all() every frequency_minutes using asyncio.sleep().

        Implements circuit breaker with exponential backoff: doubles the
        wait time on each failure up to 60 minutes, resets on success.
        Supports graceful shutdown via request_shutdown() or SIGINT/SIGTERM.
        """
        import signal

        current_wait = frequency_minutes
        max_wait = 60

        def _signal_handler() -> None:
            self.request_shutdown()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler)
            except (NotImplementedError, RuntimeError):
                pass

        while not self._shutdown_event.is_set():
            try:
                await self.sync_all()
                current_wait = frequency_minutes
            except Exception as exc:
                logger.warning("Continuous sync error: {}", exc)
                current_wait = min(current_wait * 2, max_wait)
                logger.info("Circuit breaker: next retry in {} minutes", current_wait)
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=current_wait * 60
                )
            except asyncio.TimeoutError:
                pass

    def request_shutdown(self) -> None:
        """Signal the continuous sync loop to stop gracefully."""
        self._shutdown_event.set()

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

    async def _ensure_company(self) -> str | None:
        """Return the company to use for requests, auto-detecting if needed.

        After first detection, stores it and always includes it in
        subsequent requests. Logs a warning if operating without a company.
        """
        if self._company:
            return self._company
        try:
            companies = await self._connection.get_company_list()
            if companies:
                self._company = companies[0]
                logger.info("Auto-detected Tally company: '{}'", self._company)
                return self._company
        except Exception as exc:
            logger.debug("Company auto-detection failed: {}", exc)
        logger.warning(
            "Operating without SVCURRENTCOMPANY — Tally may return data "
            "from an unexpected company. Set TALLYBRIDGE_TALLY_COMPANY "
            "or ensure only one company is open in TallyPrime."
        )
        return self._company

    def _parse_entity(
        self, entity_type: str, xml_or_json: str | dict[str, Any]
    ) -> list[Any]:
        if isinstance(xml_or_json, dict):
            return self._parse_entity_json(entity_type, xml_or_json)
        parse_map: dict[str, Any] = {
            "ledger": self._parser.parse_ledgers,
            "group": self._parser.parse_groups,
            "stock_item": self._parser.parse_stock_items,
            "voucher_type": self._parser.parse_voucher_types,
            "unit": self._parser.parse_units,
            "stock_group": self._parser.parse_stock_groups,
            "cost_center": self._parser.parse_cost_centers,
            "godown": self._parser.parse_godowns,
            "voucher": self._parser.parse_vouchers,
        }
        parse_fn = parse_map.get(entity_type)
        if parse_fn is None:
            return []
        result: list[Any] = parse_fn(xml_or_json)
        return result

    def _parse_entity_json(
        self, entity_type: str, data: dict[str, Any]
    ) -> list[Any]:
        from tallybridge.parser import TallyJSONParser

        json_parser = TallyJSONParser()
        parse_map: dict[str, Any] = {
            "ledger": json_parser.parse_ledgers_json,
            "group": json_parser.parse_groups_json,
            "stock_item": json_parser.parse_stock_items_json,
            "voucher_type": json_parser.parse_voucher_types_json,
            "unit": json_parser.parse_units_json,
            "stock_group": json_parser.parse_stock_groups_json,
            "cost_center": json_parser.parse_cost_centers_json,
            "godown": json_parser.parse_godowns_json,
            "voucher": json_parser.parse_vouchers_json,
        }
        parse_fn = parse_map.get(entity_type)
        if parse_fn is None:
            return []
        result: list[Any] = parse_fn(data)
        return result

    def _upsert_entity(
        self, entity_type: str, records: list[Any], company: str | None = None
    ) -> tuple[int, int]:
        """Upsert records and return (count, max_committed_alter_id)."""
        upsert_map: dict[str, Any] = {
            "ledger": self._cache.upsert_ledgers,
            "group": self._cache.upsert_groups,
            "stock_item": self._cache.upsert_stock_items,
            "voucher_type": self._cache.upsert_voucher_types,
            "unit": self._cache.upsert_units,
            "stock_group": self._cache.upsert_stock_groups,
            "cost_center": self._cache.upsert_cost_centers,
            "godown": self._cache.upsert_godowns,
            "voucher": self._cache.upsert_vouchers,
        }
        upsert_fn = upsert_map.get(entity_type)
        if upsert_fn is None:
            return 0, 0
        if entity_type == "voucher":
            count, max_id = upsert_fn(records, company=company)
        else:
            count = upsert_fn(records)
            max_id = max((r.alter_id for r in records), default=0)
        return count, max_id
