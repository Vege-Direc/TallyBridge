# BI Integration Guide

TallyBridge stores your TallyPrime data in a local DuckDB file (`tallybridge.duckdb` by default). This makes it easy to connect any BI tool that supports DuckDB, ODBC, or SQL queries.

## Pre-Built Views

TallyBridge creates 5 pre-built SQL views during initialization:

| View | Description |
|---|---|
| `v_sales_summary` | Sales and credit note vouchers with amounts |
| `v_receivables` | Outstanding receivables with overdue days |
| `v_gst_summary` | GST ledger totals by date |
| `v_stock_summary` | Stock items with quantities and values |
| `v_party_position` | Party receivable/payable classification |

Query them directly:

```sql
SELECT * FROM v_sales_summary WHERE voucher_date >= '2025-01-01';
SELECT party_name, outstanding_amount, overdue_days FROM v_receivables WHERE overdue_days > 30;
SELECT * FROM v_gst_summary WHERE ledger_name LIKE 'CGST%';
```

## Connecting BI Tools

### Power BI

1. Install the [DuckDB ODBC driver](https://duckdb.org/docs/extensions/odbc.html)
2. In Power BI Desktop: **Get Data** → **Other** → **ODBC**
3. Select the DuckDB driver, then enter your database path as the DSN:
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
```

### Looker

1. Use the [DuckDB JDBC driver](https://duckdb.org/docs/extensions/java)
2. Configure a Looker connection with the JDBC URL:
   ```
   jdbc:duckdb:tallybridge.duckdb?access_mode=read_only
   ```
3. Build LookML views on top of the TallyBridge SQL views

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

## HTTP API (tallybridge serve)

For BI tools that can make HTTP requests but don't support DuckDB natively:

```bash
tallybridge serve --port 8080
```

See the CLI reference for `tallybridge serve` options. This starts a read-only HTTP SQL API on your DuckDB file.

## Schema Reference

Key tables in the DuckDB database:

| Table | Description |
|---|---|
| `mst_ledger` | All ledgers with balances and GST info |
| `mst_group` | Tally group hierarchy |
| `mst_stock_item` | Stock items with HSN codes and GST rates |
| `mst_voucher_type` | Voucher type definitions |
| `mst_unit` | Units of measurement |
| `trn_voucher` | All vouchers with dates, types, narrations |
| `trn_ledger_entry` | Ledger entries within vouchers |
| `trn_inventory_entry` | Inventory entries within vouchers |
| `trn_bill` | Bill allocations with due dates |
| `trn_cost_centre` | Cost centre allocations |

## Tips

- Always use `read_only=True` when connecting BI tools to avoid write conflicts with sync
- Schedule TallyBridge sync (`tallybridge sync`) before refreshing BI dashboards
- Use the pre-built views as starting points — they handle the common JOINs
- For large datasets, DuckDB performs best with columnar queries (SELECT specific columns, not SELECT *)
