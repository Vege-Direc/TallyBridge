# BI Integration Guide

TallyBridge stores your TallyPrime data in a local DuckDB file (`tallybridge.duckdb` by default). This makes it easy to connect any BI tool that supports DuckDB, ODBC, or SQL queries.

## Pre-Built Views

TallyBridge creates 5 pre-built SQL views during initialization:

| View | Description | Key Columns |
|---|---|---|
| `v_sales_summary` | Sales and credit note vouchers | `voucher_date`, `voucher_type`, `party_name`, `total_amount` |
| `v_receivables` | Outstanding receivables with aging | `party_name`, `outstanding_amount`, `overdue_days` |
| `v_gst_summary` | GST ledger totals by date | `date`, `ledger_name`, `amount` |
| `v_stock_summary` | Stock items with quantities and values | `name`, `unit`, `closing_quantity`, `closing_value` |
| `v_party_position` | Party receivable/payable classification | `party_name`, `total_receivable`, `total_payable` |

Query them directly:

```sql
SELECT * FROM v_sales_summary WHERE voucher_date >= '2025-01-01';
SELECT party_name, outstanding_amount, overdue_days
  FROM v_receivables WHERE overdue_days > 30;
SELECT * FROM v_gst_summary WHERE ledger_name LIKE 'CGST%';
```

## Connecting BI Tools

### Power BI

1. Install the [DuckDB ODBC driver](https://duckdb.org/docs/extensions/odbc.html)
2. In Power BI Desktop: **Get Data** → **Other** → **ODBC**
3. Enter your database path as the DSN:
   ```
   Driver={DuckDB Driver};Database=tallybridge.duckdb;access_mode=read_only
   ```
4. Select the views or tables you want to visualize

### Metabase

1. Install the [DuckDB Metabase driver](https://github.com/AntonDobkin/metabase-duckdb-driver)
2. Add a new database connection:
   - **Database type**: DuckDB
   - **Database file**: path to `tallybridge.duckdb`
   - **Read-only**: Yes
3. Use the pre-built views as starting points for dashboards

### Apache Superset

1. Install the `duckdb-engine` Python package:
   ```bash
   pip install duckdb-engine
   ```
2. In Superset: **Data** → **Databases** → **+ Database**
3. Select **SQLAlchemy** and enter:
   ```
   duckdb:///tallybridge.duckdb?access_mode=read_only
   ```
4. Create datasets from the pre-built views

### Excel / Google Sheets

**Option A: ODBC** (Excel on Windows)
1. Install the DuckDB ODBC driver
2. **Data** → **Get Data** → **From Other Sources** → **From ODBC**
3. Connect to the DuckDB DSN and select your view

**Option B: CSV Export** (any spreadsheet)
```bash
# Export any view to CSV using DuckDB CLI
duckdb tallybridge.duckdb -c "COPY v_sales_summary TO 'sales.csv' (HEADER, DELIMITER ',')"

# Or use TallyBridge CLI
tallybridge export csv --table ledgers --output ledgers.csv
tallybridge export csv --table vouchers --where "date >= '2025-01-01'" --output vouchers.csv
```

**Option C: Excel Export** (multi-sheet)
```bash
# Requires pip install tallybridge[excel]
tallybridge export excel --output tally_data.xlsx
```

### Looker

1. Use the [DuckDB JDBC driver](https://duckdb.org/docs/extensions/java)
2. Configure a Looker connection with the JDBC URL:
   ```
   jdbc:duckdb:tallybridge.duckdb?access_mode=read_only
   ```
3. Build LookML views on top of the TallyBridge SQL views

## HTTP API (tallybridge serve)

For BI tools that can make HTTP requests but don't support DuckDB natively:

```bash
pip install tallybridge[serve]
tallybridge serve --port 8080
```

Endpoints:

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | API info |
| `GET` | `/health` | Health check |
| `GET` | `/views` | List all BI views |
| `GET` | `/views/{name}` | Query a view |
| `POST` | `/query` | Execute read-only SQL |
| `GET` | `/tables` | List all tables |

```bash
# Query a view
curl http://localhost:8080/views/v_sales_summary

# Execute custom SQL
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM mst_ledger LIMIT 10"}'
```

## Direct SQL Access

Use the DuckDB CLI or Python for ad-hoc queries:

```bash
# DuckDB CLI
duckdb tallybridge.duckdb -c "SELECT * FROM v_party_position"

# Python
import duckdb
conn = duckdb.connect("tallybridge.duckdb", read_only=True)
df = conn.execute("SELECT * FROM v_sales_summary").df()
conn.close()
```

## Schema Reference

### Master Tables

| Table | Description | Key Columns |
|---|---|---|
| `mst_ledger` | All ledgers with balances and GST info | `name`, `parent_group`, `closing_balance`, `gstin` |
| `mst_group` | Tally group hierarchy | `name`, `parent`, `primary_group` |
| `mst_stock_item` | Stock items with HSN codes and GST rates | `name`, `unit`, `gst_rate`, `hsn_code`, `closing_quantity` |
| `mst_godown` | Warehouse/godown locations | `name`, `parent` |
| `mst_voucher_type` | Voucher type definitions | `name`, `parent` |
| `mst_unit` | Units of measurement | `name`, `unit_type`, `symbol` |
| `mst_stock_group` | Stock item groupings | `name`, `parent` |
| `mst_cost_center` | Cost centres for project/department tracking | `name`, `parent` |

### Transaction Tables

| Table | Description | Key Columns |
|---|---|---|
| `trn_voucher` | All vouchers with dates, types, narrations | `date`, `voucher_type`, `party_ledger`, `total_amount`, `gst_amount` |
| `trn_ledger_entry` | Ledger entries within vouchers | `voucher_guid`, `ledger_name`, `amount` |
| `trn_inventory_entry` | Inventory entries within vouchers | `voucher_guid`, `stock_item_name`, `quantity`, `rate` |
| `trn_bill` | Bill allocations with due dates | `voucher_guid`, `bill_name`, `amount`, `bill_credit_period` |
| `trn_cost_centre` | Cost centre allocations | `voucher_guid`, `ledger_name`, `cost_centre`, `amount` |

### System Tables

| Table | Description |
|---|---|
| `sync_state` | Sync progress tracking per entity (alter_id, last_sync_at) |
| `sync_errors` | Failed record tracking (entity_type, guid, error_message) |
| `audit_log` | Write operation audit trail (operation, entity, timestamp) |
| `schema_version` | Database migration version tracking |

## Tips

- Always use `read_only=True` when connecting BI tools to avoid write conflicts with sync
- Schedule TallyBridge sync (`tallybridge sync`) before refreshing BI dashboards
- Use the pre-built views as starting points — they handle the common JOINs
- For large datasets, DuckDB performs best with columnar queries (`SELECT` specific columns, not `SELECT *`)
- Use `tallybridge export csv --where` for filtered exports instead of pulling entire tables
