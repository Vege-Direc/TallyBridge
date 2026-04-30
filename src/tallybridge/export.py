"""Data export module — see SPECS.md §35."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from tallybridge.cache import TallyCache

VALID_TABLES = frozenset(
    {
        "ledgers",
        "groups",
        "stock_items",
        "voucher_types",
        "units",
        "stock_groups",
        "cost_centers",
        "godowns",
        "vouchers",
        "ledger_entries",
        "inventory_entries",
        "cost_centre_entries",
        "bill_entries",
        "sync_errors",
    }
)

_SAFE_WHERE_PATTERN = re.compile(
    r";|--|/\*|\bUNION\b|\bDROP\b|\bDELETE\b|\bINSERT\b|\bUPDATE\b"
    r"|\bALTER\b|\bCREATE\b|\bATTACH\b",
    re.IGNORECASE,
)

_VALID_COLUMN_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

_TABLE_NAME_MAP: dict[str, str] = {
    "ledgers": "mst_ledger",
    "groups": "mst_group",
    "stock_items": "mst_stock_item",
    "voucher_types": "mst_voucher_type",
    "units": "mst_unit",
    "stock_groups": "mst_stock_group",
    "cost_centers": "mst_cost_center",
    "godowns": "mst_godown",
    "vouchers": "trn_voucher",
    "ledger_entries": "trn_ledger_entry",
    "inventory_entries": "trn_inventory_entry",
    "cost_centre_entries": "trn_cost_centre",
    "bill_entries": "trn_bill",
    "sync_errors": "sync_errors",
}

_DEFAULT_TABLES = [
    "ledgers",
    "groups",
    "stock_items",
    "vouchers",
    "ledger_entries",
    "inventory_entries",
]


def _validate_columns(columns: list[str] | None) -> None:
    if columns is None:
        return
    for col in columns:
        if not _VALID_COLUMN_PATTERN.match(col):
            raise ValueError(f"Invalid column name: '{col}'")


def _validate_where(where: str | None) -> None:
    if where is None:
        return
    if _SAFE_WHERE_PATTERN.search(where):
        raise ValueError(
            "WHERE clause contains disallowed SQL keywords. "
            "Only simple conditions are allowed (e.g. 'name = ?' style)."
        )


def _validate_output_path(output_path: str | Path) -> Path:
    path = Path(output_path).resolve()
    if ".." in Path(output_path).parts:
        raise ValueError(
            "Output path must not contain '..' directory traversal components."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_table(table: str) -> str:
    resolved = _TABLE_NAME_MAP.get(table)
    if resolved is None:
        if table in _TABLE_NAME_MAP.values():
            return table
        raise ValueError(
            f"Unknown table '{table}'. Valid: {sorted(VALID_TABLES)}"
        )
    return resolved


def _serialize_row(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, float):
        return str(value)
    return value


class DataExporter:
    """Export cached Tally data to CSV, Excel, and JSON formats."""

    def __init__(self, cache: TallyCache) -> None:
        self._cache = cache

    def _fetch_data(
        self,
        table: str,
        columns: list[str] | None = None,
        where: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        return self.fetch_data(table, columns, where, limit)

    def fetch_data(
        self,
        table: str,
        columns: list[str] | None = None,
        where: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        db_table = _resolve_table(table)
        _validate_columns(columns)
        _validate_where(where)
        col_clause = ", ".join(columns) if columns else "*"
        sql = f"SELECT {col_clause} FROM {db_table}"
        params: list[Any] = []
        if where:
            sql += f" WHERE {where}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = self._cache.query(sql, params)
        if not rows:
            col_names = columns or []
            return col_names, []
        col_names = list(rows[0].keys())
        return col_names, rows

    def export_csv(
        self,
        table: str,
        output_path: str | Path,
        columns: list[str] | None = None,
        where: str | None = None,
        limit: int | None = None,
    ) -> int:
        """Export a cache table/query to CSV. Returns row count."""
        col_names, rows = self._fetch_data(table, columns, where, limit)
        path = _validate_output_path(output_path)
        with open(path, "w", newline="", encoding="utf-8") as f:
            if not rows and not col_names:
                f.write("")
                return 0
            writer = csv.DictWriter(
                f, fieldnames=col_names, extrasaction="ignore"
            )
            writer.writeheader()
            for row in rows:
                serialized = {k: _serialize_row(v) for k, v in row.items()}
                writer.writerow(serialized)
        logger.info("Exported {} rows to CSV: {}", len(rows), path)
        return len(rows)

    def export_excel(
        self,
        output_path: str | Path,
        tables: list[str] | None = None,
    ) -> dict[str, int]:
        """Export multiple tables to Excel (one sheet per table).

        Returns {table_name: row_count}.
        Requires openpyxl: pip install tallybridge[excel]
        """
        try:
            import openpyxl
        except ImportError:
            raise ImportError(
                "Excel export requires openpyxl. "
                "Install with: pip install tallybridge[excel]"
            ) from None

        table_list = tables or _DEFAULT_TABLES
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        result: dict[str, int] = {}
        for table in table_list:
            try:
                col_names, rows = self._fetch_data(table)
            except Exception as exc:
                logger.warning("Skipping table {} for Excel export: {}", table, exc)
                continue
            ws = wb.create_sheet(title=table[:31])
            if col_names:
                ws.append(col_names)
            for row in rows:
                ws.append([_serialize_row(row.get(c)) for c in col_names])
            result[table] = len(rows)

        path = _validate_output_path(output_path)
        wb.save(str(path))
        logger.info("Exported {} tables to Excel: {}", len(result), path)
        return result

    def export_json(
        self,
        table: str,
        output_path: str | Path,
        columns: list[str] | None = None,
        where: str | None = None,
        limit: int | None = None,
    ) -> int:
        """Export a cache table/query to JSON. Returns row count."""
        _, rows = self._fetch_data(table, columns, where, limit)
        serialized = [
            {k: _serialize_row(v) for k, v in row.items()} for row in rows
        ]
        path = _validate_output_path(output_path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, ensure_ascii=False, default=str)
        logger.info("Exported {} rows to JSON: {}", len(rows), path)
        return len(rows)

    def export_csv_chunked(
        self,
        table: str,
        output_path: str | Path,
        columns: list[str] | None = None,
        where: str | None = None,
        chunk_size: int = 5000,
    ) -> int:
        """Export a cache table to CSV using chunked iteration.

        Memory-efficient for large tables (100k+ rows).
        Returns row count.
        """
        db_table = _resolve_table(table)
        _validate_columns(columns)
        _validate_where(where)
        col_clause = ", ".join(columns) if columns else "*"
        sql = f"SELECT {col_clause} FROM {db_table}"
        if where:
            sql += f" WHERE {where}"

        path = _validate_output_path(output_path)

        total = 0
        header_written = False
        col_names: list[str] = columns or []

        with open(path, "w", newline="", encoding="utf-8") as f:
            for chunk in self._cache.query_iter(sql, chunk_size=chunk_size):
                if not chunk:
                    continue
                if not header_written:
                    col_names = col_names or list(chunk[0].keys())
                    writer = csv.DictWriter(
                        f, fieldnames=col_names, extrasaction="ignore"
                    )
                    writer.writeheader()
                    header_written = True
                for row in chunk:
                    serialized = {k: _serialize_row(v) for k, v in row.items()}
                    writer.writerow(serialized)
                total += len(chunk)

        logger.info("Chunked exported {} rows to CSV: {}", total, path)
        return total

    def export_csv_bytes(
        self,
        table: str,
        columns: list[str] | None = None,
        where: str | None = None,
        limit: int | None = None,
    ) -> str:
        """Export a cache table to CSV string (for MCP tool)."""
        col_names, rows = self._fetch_data(table, columns, where, limit)
        if not rows and not col_names:
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(
            output, fieldnames=col_names, extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows:
            serialized = {k: _serialize_row(v) for k, v in row.items()}
            writer.writerow(serialized)
        return output.getvalue()
