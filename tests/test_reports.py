"""Tests for scheduled report generation — see SPECS.md §37."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tallybridge.cache import TallyCache
from tallybridge.models.master import TallyLedger
from tallybridge.models.voucher import (
    TallyVoucher,
    TallyVoucherEntry,
)
from tallybridge.query import TallyQuery
from tallybridge.reports import ReportScheduler


@pytest.fixture
def populated_cache(tmp_path: Path) -> TallyCache:
    db = TallyCache(str(tmp_path / "test.duckdb"))
    db.upsert_ledgers(
        [
            TallyLedger(
                name="Cash",
                guid="g-cash",
                alter_id=1,
                parent_group="Cash-in-Hand",
                closing_balance=Decimal("50000"),
            ),
            TallyLedger(
                name="Sales",
                guid="g-sales",
                alter_id=2,
                parent_group="Sales Accounts",
                closing_balance=Decimal("120000"),
            ),
        ]
    )
    db.upsert_vouchers(
        [
            TallyVoucher(
                guid="v-001",
                alter_id=100,
                voucher_number="SI/001",
                voucher_type="Sales",
                date=date(2026, 4, 1),
                party_ledger="Customer A",
                total_amount=Decimal("59000"),
                gst_amount=Decimal("9000"),
                ledger_entries=[
                    TallyVoucherEntry(
                        ledger_name="Customer A", amount=Decimal("59000")
                    ),
                    TallyVoucherEntry(
                        ledger_name="Sales", amount=Decimal("-50000")
                    ),
                ],
            ),
        ]
    )
    return db


@pytest.fixture
def scheduler(populated_cache: TallyCache) -> ReportScheduler:
    query = TallyQuery(populated_cache)
    return ReportScheduler(populated_cache, query)


def test_generate_daily_digest_report(
    scheduler: ReportScheduler, tmp_path: Path
) -> None:
    output = tmp_path / "digest.json"
    path = scheduler.generate_report(
        "daily_digest",
        as_of_date=date(2026, 4, 1),
        output_path=str(output),
    )
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "total_sales" in data


def test_generate_gst_summary_csv(scheduler: ReportScheduler, tmp_path: Path) -> None:
    output = tmp_path / "gst.csv"
    path = scheduler.generate_report(
        "gst_summary",
        as_of_date=date(2026, 4, 1),
        output_format="csv",
        output_path=str(output),
    )
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert len(content) > 0


def test_generate_report_html(scheduler: ReportScheduler, tmp_path: Path) -> None:
    output = tmp_path / "report.html"
    path = scheduler.generate_report(
        "receivables",
        as_of_date=date(2026, 4, 1),
        output_format="html",
        output_path=str(output),
    )
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "<html>" in content
    assert "Receivables" in content


def test_generate_report_default_path(scheduler: ReportScheduler) -> None:
    path = scheduler.generate_report("stock_summary", as_of_date=date(2026, 4, 1))
    assert path.exists()
    path.unlink()


def test_add_schedule(scheduler: ReportScheduler) -> None:
    scheduler.add_schedule(
        report_type="daily_digest",
        frequency="daily",
        output_dir="/tmp/reports",
    )
    assert len(scheduler._schedules) == 1
    assert scheduler._schedules[0]["report_type"] == "daily_digest"


def test_run_pending_first_run(scheduler: ReportScheduler, tmp_path: Path) -> None:
    scheduler.add_schedule(
        report_type="stock_summary",
        frequency="daily",
        output_dir=str(tmp_path),
    )
    generated = scheduler.run_pending()
    assert len(generated) == 1


def test_run_pending_not_due(scheduler: ReportScheduler, tmp_path: Path) -> None:
    from datetime import datetime

    scheduler.add_schedule(
        report_type="stock_summary",
        frequency="daily",
        output_dir=str(tmp_path),
    )
    scheduler._schedules[0]["last_run"] = datetime.now().isoformat()
    generated = scheduler.run_pending()
    assert len(generated) == 0


def test_send_email_no_smtp(scheduler: ReportScheduler) -> None:
    result = scheduler.send_email(
        recipients=["test@example.com"],
        subject="Test",
        body="Hello",
    )
    assert result is False


def test_send_email_mock(scheduler: ReportScheduler) -> None:
    scheduler._smtp_config = {
        "host": "smtp.example.com",
        "port": 587,
        "use_tls": True,
        "from": "test@example.com",
        "username": "user",
        "password": "pass",
    }
    with patch("tallybridge.reports.smtplib.SMTP") as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance
        result = scheduler.send_email(
            recipients=["recipient@example.com"],
            subject="Test Report",
            body="Report attached",
        )
        assert result is True
        mock_instance.starttls.assert_called_once()
        mock_instance.login.assert_called_once_with("user", "pass")
        mock_instance.send_message.assert_called_once()


def test_send_email_smtp_failure(scheduler: ReportScheduler) -> None:
    scheduler._smtp_config = {
        "host": "smtp.example.com",
        "port": 587,
        "use_tls": True,
    }
    with patch(
        "tallybridge.reports.smtplib.SMTP",
        side_effect=Exception("Connection failed"),
    ):
        result = scheduler.send_email(
            recipients=["test@example.com"],
            subject="Test",
            body="Hello",
        )
        assert result is False
