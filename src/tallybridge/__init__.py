"""TallyBridge — sync TallyPrime to DuckDB and AI via MCP."""

from tallybridge.config import TallyBridgeConfig, get_config
from tallybridge.connection import TallyConnection
from tallybridge.cache import TallyCache
from tallybridge.sync import TallySyncEngine
from tallybridge.models.report import SyncResult
from tallybridge.query import TallyQuery
from tallybridge.parser import TallyXMLParser
from tallybridge.models.master import (
    TallyLedger,
    TallyGroup,
    TallyStockItem,
    TallyUnit,
    TallyStockGroup,
    TallyCostCenter,
)
from tallybridge.models.voucher import TallyVoucher, TallyVoucherEntry
from tallybridge.models.report import (
    DailyDigest,
    OutstandingBill,
    TrialBalanceLine,
    StockAgingLine,
)
from tallybridge.exceptions import (
    TallyConnectionError,
    TallyDataError,
    TallySyncError,
    TallyBridgeCacheError,
)


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
        print(f"Today's sales: ₹{digest.total_sales:,.0f}")

    Raises:
        TallyConnectionError: If TallyPrime is not running.
    """
    config = TallyBridgeConfig(
        tally_host=tally_host,
        tally_port=tally_port,
        db_path=db_path,
        tally_company=company,
    )
    cache = TallyCache(db_path)
    cache.initialize()
    import asyncio
    connection = TallyConnection(config)
    parser = TallyXMLParser()
    engine = TallySyncEngine(connection, cache, parser)
    asyncio.run(engine.sync_all())
    return TallyQuery(cache)


__version__ = "0.1.0"
__all__ = [
    "connect",
    "__version__",
    "TallyBridgeConfig", "get_config",
    "TallyConnection",
    "TallyCache",
    "TallySyncEngine", "SyncResult",
    "TallyQuery",
    "TallyXMLParser",
    "TallyLedger", "TallyGroup", "TallyStockItem",
    "TallyUnit", "TallyStockGroup", "TallyCostCenter",
    "TallyVoucher", "TallyVoucherEntry",
    "DailyDigest", "OutstandingBill", "TrialBalanceLine", "StockAgingLine",
    "TallyConnectionError", "TallyDataError",
    "TallySyncError", "TallyBridgeCacheError",
]
