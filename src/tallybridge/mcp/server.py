"""MCP server — see SPECS.md §9b."""

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from loguru import logger

from tallybridge.cache import TallyCache
from tallybridge.config import TallyBridgeConfig, get_config
from tallybridge.mcp.tools import TOOLS
from tallybridge.query import TallyQuery

FORBIDDEN_SQL = frozenset([
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
    "CREATE", "TRUNCATE", "EXEC", "EXECUTE",
])


def is_safe_sql(sql: str) -> bool:
    """Check if SQL query is read-only (SELECT only)."""
    tokens = sql.upper().split()
    return not any(t in FORBIDDEN_SQL for t in tokens)


class TallyMCPServer:
    """MCP server that dispatches tool calls to TallyQuery."""

    def __init__(self, config: TallyBridgeConfig | None = None) -> None:
        self._config = config or get_config()
        self._cache = TallyCache(self._config.db_path)
        self._query = TallyQuery(self._cache)

    def list_tools(self) -> list[dict]:
        """Return the list of available tools."""
        return TOOLS

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict:
        """Dispatch a tool call to the appropriate TallyQuery method."""
        try:
            result = self._dispatch(name, arguments)
            return self._serialize(result)
        except Exception as exc:
            logger.warning("Tool '{}' error: {}", name, exc)
            return {"error": True, "message": str(exc), "tool": name}

    def _dispatch(self, name: str, args: dict[str, Any]) -> Any:
        if name == "get_tally_digest":
            d = self._parse_date(args.get("date"))
            return self._query.get_daily_digest(d)

        if name == "get_ledger_balance":
            return {
                "ledger_name": args["ledger_name"],
                "balance": str(self._query.get_ledger_balance(args["ledger_name"])),
            }

        if name == "get_receivables":
            return self._query.get_receivables(
                overdue_only=args.get("overdue_only", False),
                min_days_overdue=args.get("min_days_overdue", 0),
            )

        if name == "get_party_outstanding":
            return self._query.get_party_outstanding(args["party_name"])

        if name == "get_sales_summary":
            return self._query.get_sales_summary(
                from_date=self._parse_date(args["from_date"]) or date.today(),
                to_date=self._parse_date(args["to_date"]) or date.today(),
                group_by=args.get("group_by", "day"),
            )

        if name == "get_gst_summary":
            return self._query.get_gst_summary(
                from_date=self._parse_date(args["from_date"]) or date.today(),
                to_date=self._parse_date(args["to_date"]) or date.today(),
            )

        if name == "search_tally":
            return self._query.search(
                query=args["query"],
                limit=args.get("limit", 20),
            )

        if name == "get_sync_status":
            return self._cache.get_sync_status()

        if name == "get_low_stock":
            items = self._query.get_low_stock_items(
                threshold_quantity=Decimal(str(args.get("threshold", 0)))
            )
            return [{"name": i.name, "closing_quantity": str(i.closing_quantity)} for i in items]

        if name == "get_stock_aging":
            bucket_days = args.get("bucket_days")
            return self._query.get_stock_aging(
                as_of_date=self._parse_date(args.get("date")),
                bucket_days=bucket_days if bucket_days else None,
            )

        if name == "get_cost_center_summary":
            return self._query.get_cost_center_summary(
                from_date=self._parse_date(args["from_date"]) or date.today(),
                to_date=self._parse_date(args["to_date"]) or date.today(),
                cost_center_name=args.get("cost_center_name"),
            )

        if name == "query_tally_data":
            sql = args["sql"]
            if not is_safe_sql(sql):
                return {"error": True, "message": "Only SELECT queries are allowed. Forbidden keywords detected.", "tool": name}
            limit = args.get("limit", 1000)
            if "LIMIT" not in sql.upper():
                sql = sql + f" LIMIT {limit}"
            return self._cache.query(sql)

        return {"error": True, "message": f"Unknown tool: {name}", "tool": name}

    def _serialize(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, list):
            return [self._serialize(item) for item in obj]
        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        if hasattr(obj, "model_dump"):
            return self._serialize(obj.model_dump())
        return obj

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value.strip():
            return date.fromisoformat(value.strip())
        return None

    def run_stdio(self) -> None:
        """Run MCP server using stdio transport."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue

            method = message.get("method")
            msg_id = message.get("id")

            if method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"tools": self.list_tools()},
                }
            elif method == "tools/call":
                params = message.get("params", {})
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = self.call_tool(tool_name, arguments)
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(self._serialize(result))}]},
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {},
                }

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

    def close(self) -> None:
        self._cache.close()
