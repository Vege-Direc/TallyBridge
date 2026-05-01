"""TallyBridge — sync TallyPrime to DuckDB and AI via MCP."""

from tallybridge.cache import TallyCache
from tallybridge.client import TallyBridge
from tallybridge.config import TallyBridgeConfig, get_config
from tallybridge.connection import TallyConnection
from tallybridge.exceptions import (
    TallyBridgeCacheError,
    TallyConnectionError,
    TallyDataError,
    TallySyncError,
)
from tallybridge.models.master import (
    TallyCostCenter,
    TallyGroup,
    TallyLedger,
    TallyStockGroup,
    TallyStockItem,
    TallyUnit,
)
from tallybridge.models.report import (
    DailyDigest,
    GSTR1Result,
    GSTR2AClaim,
    GSTR3BResult,
    GSTR9Result,
    ImportResult,
    OutstandingBill,
    ReconciliationResult,
    StockAgingLine,
    SyncResult,
    TrialBalanceLine,
    ValidationResult,
)
from tallybridge.models.voucher import TallyVoucher, TallyVoucherEntry
from tallybridge.parser import TallyJSONParser, TallyXMLParser
from tallybridge.query import TallyQuery
from tallybridge.sync import TallySyncEngine
from tallybridge.version import TallyProduct, detect_tally_version


def connect(
    tally_host: str = "localhost",
    tally_port: int = 9000,
    db_path: str = "tallybridge.duckdb",
    company: str | None = None,
) -> TallyBridge:
    """Connect to TallyBridge: sync, query, and write-back.

    The simplest possible entry point for new users. Syncs on first call
    and returns a :class:`TallyBridge` object supporting read, write,
    and sync operations.

    Example::

        import tallybridge
        tb = tallybridge.connect()
        digest = tb.get_daily_digest()
        print(f"Today's sales: {digest.total_sales:,.0f}")

    Raises:
        TallyConnectionError: If TallyPrime is not running.
    """
    import asyncio

    config = TallyBridgeConfig(
        tally_host=tally_host,
        tally_port=tally_port,
        db_path=db_path,
        tally_company=company,
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        def _run_sync() -> TallyBridge:
            bridge = TallyBridge(config)
            asyncio.run(bridge.sync())
            return bridge

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run_sync).result()
    else:
        bridge = TallyBridge(config)
        asyncio.run(bridge.sync())
        return bridge


__version__ = "0.2.0"
__all__ = [
    "connect",
    "__version__",
    "TallyBridge",
    "TallyBridgeConfig",
    "get_config",
    "TallyConnection",
    "TallyCache",
    "TallySyncEngine",
    "SyncResult",
    "ImportResult",
    "GSTR3BResult",
    "GSTR1Result",
    "TallyQuery",
    "TallyXMLParser",
    "TallyJSONParser",
    "TallyLedger",
    "TallyGroup",
    "TallyStockItem",
    "TallyUnit",
    "TallyStockGroup",
    "TallyCostCenter",
    "TallyVoucher",
    "TallyVoucherEntry",
    "DailyDigest",
    "OutstandingBill",
    "TrialBalanceLine",
    "StockAgingLine",
    "TallyConnectionError",
    "TallyDataError",
    "TallySyncError",
    "TallyBridgeCacheError",
    "ValidationResult",
    "GSTR2AClaim",
    "ReconciliationResult",
    "GSTR9Result",
    "TallyProduct",
    "detect_tally_version",
]
