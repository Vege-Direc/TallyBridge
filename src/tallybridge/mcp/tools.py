"""MCP tool definitions — see SPECS.md §9a."""

TOOLS: list[dict] = [
    {
        "name": "get_tally_digest",
        "description": "Complete business summary: sales, purchases, balances, overdue parties",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format (default: today)",
                },
            },
        },
    },
    {
        "name": "get_ledger_balance",
        "description": "Closing balance of any ledger. Positive=Dr, Negative=Cr",
        "inputSchema": {
            "type": "object",
            "required": ["ledger_name"],
            "properties": {
                "ledger_name": {"type": "string", "description": "Ledger name"},
                "date": {"type": "string", "description": "As-of date (YYYY-MM-DD)"},
            },
        },
    },
    {
        "name": "get_receivables",
        "description": "Outstanding sales invoices — money owed to the business",
        "inputSchema": {
            "type": "object",
            "properties": {
                "overdue_only": {"type": "boolean", "description": "Only past-due bills"},
                "min_days_overdue": {"type": "integer", "description": "Minimum days overdue"},
            },
        },
    },
    {
        "name": "get_party_outstanding",
        "description": "Full receivable/payable position with one party",
        "inputSchema": {
            "type": "object",
            "required": ["party_name"],
            "properties": {
                "party_name": {"type": "string", "description": "Party name"},
            },
        },
    },
    {
        "name": "get_sales_summary",
        "description": "Sales by day/week/month/party/item for a date range",
        "inputSchema": {
            "type": "object",
            "required": ["from_date", "to_date"],
            "properties": {
                "from_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "to_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "group_by": {
                    "type": "string",
                    "enum": ["day", "week", "month", "party", "item"],
                    "description": "Grouping dimension (default: day)",
                },
            },
        },
    },
    {
        "name": "get_gst_summary",
        "description": "GST collected, ITC, and net liability for a period",
        "inputSchema": {
            "type": "object",
            "required": ["from_date", "to_date"],
            "properties": {
                "from_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "to_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
            },
        },
    },
    {
        "name": "search_tally",
        "description": "Search ledgers, parties, voucher narrations",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "Search string"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
        },
    },
    {
        "name": "get_sync_status",
        "description": "When data was last synced and record counts",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_low_stock",
        "description": "Stock items at or below quantity threshold",
        "inputSchema": {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "description": "Quantity threshold (default 0)"},
            },
        },
    },
    {
        "name": "get_stock_aging",
        "description": "How long stock has been sitting — aging by day buckets",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "As-of date (YYYY-MM-DD)"},
                "bucket_days": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Aging bucket boundaries in days (default [30,60,90,180])",
                },
            },
        },
    },
    {
        "name": "get_cost_center_summary",
        "description": "Income and expense breakdown by department or project cost centre",
        "inputSchema": {
            "type": "object",
            "required": ["from_date", "to_date"],
            "properties": {
                "from_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "to_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "cost_center_name": {"type": "string", "description": "Filter to one cost centre"},
            },
        },
    },
    {
        "name": "query_tally_data",
        "description": "Run a custom SQL SELECT on the local cache. Tables: mst_ledger, mst_group, mst_stock_item, mst_unit, mst_stock_group, mst_cost_center, trn_voucher, trn_ledger_entry, trn_inventory_entry",
        "inputSchema": {
            "type": "object",
            "required": ["sql"],
            "properties": {
                "sql": {"type": "string", "description": "SELECT SQL query"},
                "limit": {"type": "integer", "description": "Max rows (default 1000)"},
            },
        },
    },
]
