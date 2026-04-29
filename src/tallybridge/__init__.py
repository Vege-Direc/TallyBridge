"""TallyBridge — sync TallyPrime to DuckDB and AI via MCP."""

from tallybridge.cache import TallyCache
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
    GSTR3BResult,
    ImportResult,
    OutstandingBill,
    StockAgingLine,
    SyncResult,
    TrialBalanceLine,
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
) -> TallyQuery:
    """Connect to TallyBridge: sync fresh data from Tally, return TallyQuery.

    The simplest possible entry point for new users.

    Example:
        import tallybridge
        q = tallybridge.connect()
        digest = q.get_daily_digest()
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
    cache = TallyCache(db_path)
    cache.initialize()
    connection = TallyConnection(config)
    parser = TallyXMLParser()
    engine = TallySyncEngine(connection, cache, parser)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        def _run_sync() -> None:
            asyncio.run(engine.sync_all())
            asyncio.run(connection.close())

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(_run_sync).result()
    else:
        asyncio.run(engine.sync_all())
        asyncio.run(connection.close())

    return TallyQuery(cache)


__version__ = "0.1.0"
__all__ = [
    "connect",
    "__version__",
    "TallyBridgeConfig",
    "get_config",
    "TallyConnection",
    "TallyCache",
    "TallySyncEngine",
    "SyncResult",
    "ImportResult",
    "GSTR3BResult",
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
    "TallyProduct",
    "detect_tally_version",
]
