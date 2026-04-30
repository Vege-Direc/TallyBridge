"""Scheduled report generation — see SPECS.md §37."""

from __future__ import annotations

import asyncio
import csv
import json
import smtplib
from datetime import date, datetime, timedelta
from decimal import Decimal
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Literal

from loguru import logger

from tallybridge.cache import TallyCache
from tallybridge.query import TallyQuery

ReportType = Literal[
    "daily_digest",
    "gst_summary",
    "receivables",
    "payables",
    "stock_summary",
    "einvoice_summary",
]

OutputFormat = Literal["json", "csv", "html"]


class ReportScheduler:
    """Generate and optionally email scheduled reports."""

    def __init__(
        self,
        cache: TallyCache,
        query: TallyQuery,
        smtp_config: dict[str, Any] | None = None,
    ) -> None:
        self._cache = cache
        self._query = query
        self._smtp_config = smtp_config
        self._schedules: list[dict[str, Any]] = []

    def generate_report(
        self,
        report_type: ReportType,
        as_of_date: date | None = None,
        output_format: OutputFormat = "json",
        output_path: str | Path | None = None,
    ) -> Path:
        """Generate a report and save to file. Returns file path."""
        as_of_date = as_of_date or date.today()
        data = self._collect_report_data(report_type, as_of_date)

        if output_path is None:
            date_str = as_of_date.isoformat()
            ext = output_format
            output_path = Path(f"report_{report_type}_{date_str}.{ext}")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if output_format == "json":
            self._write_json(data, path)
        elif output_format == "csv":
            self._write_csv(data, path)
        elif output_format == "html":
            self._write_html(report_type, data, path)

        logger.info("Generated {} report: {}", report_type, path)
        return path

    def add_schedule(
        self,
        report_type: ReportType,
        frequency: Literal["daily", "weekly", "monthly"],
        output_dir: str,
        output_format: OutputFormat = "json",
        email_recipients: list[str] | None = None,
    ) -> None:
        """Register a scheduled report."""
        self._schedules.append(
            {
                "report_type": report_type,
                "frequency": frequency,
                "output_dir": output_dir,
                "output_format": output_format,
                "email_recipients": email_recipients or [],
                "last_run": None,
            }
        )

    async def run_scheduled(
        self,
        report_type: str,
        frequency: Literal["daily", "weekly", "monthly"],
        output_dir: str,
        email_recipients: list[str] | None = None,
    ) -> None:
        """Run a report on schedule. Integrates with run_continuous()."""
        interval = self._frequency_to_seconds(frequency)
        while True:
            path = self.generate_report(
                report_type=report_type,  # type: ignore[arg-type]
                output_format="json",
                output_path=str(
                    Path(output_dir)
                    / f"report_{report_type}_{date.today().isoformat()}.json"
                ),
            )
            if email_recipients:
                self.send_email(
                    recipients=email_recipients,
                    subject=f"TallyBridge {report_type} report - {date.today()}",
                    body=f"Attached: {report_type} report for {date.today()}",
                    attachments=[path],
                )
            logger.info("Scheduled {} report generated: {}", report_type, path)
            await asyncio.sleep(interval)

    def run_pending(self) -> list[Path]:
        """Check schedules and generate any reports that are due.

        Returns list of generated report paths.
        """
        generated: list[Path] = []
        now = datetime.now()
        for schedule in self._schedules:
            if self._is_due(schedule, now):
                path = self.generate_report(
                    report_type=schedule["report_type"],
                    output_format=schedule["output_format"],
                    output_path=str(
                        Path(schedule["output_dir"])
                        / f"report_{schedule['report_type']}_{date.today().isoformat()}"
                        f".{schedule['output_format']}"
                    ),
                )
                generated.append(path)
                schedule["last_run"] = now.isoformat()
                if schedule["email_recipients"]:
                    self.send_email(
                        recipients=schedule["email_recipients"],
                        subject=(
                            f"TallyBridge {schedule['report_type']} report "
                            f"- {date.today()}"
                        ),
                        body=(
                            f"Attached: {schedule['report_type']} report "
                            f"for {date.today()}"
                        ),
                        attachments=[path],
                    )
        return generated

    def send_email(
        self,
        recipients: list[str],
        subject: str,
        body: str,
        attachments: list[Path] | None = None,
    ) -> bool:
        """Send email with optional attachments. Returns success."""
        if not self._smtp_config:
            logger.warning("SMTP not configured — skipping email to {}", recipients)
            return False

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._smtp_config.get("from", "tallybridge@localhost")
        msg["To"] = ", ".join(recipients)
        msg.set_content(body)

        if attachments:
            for attachment in attachments:
                data = attachment.read_bytes()
                maintype = "text"
                subtype = "plain" if attachment.suffix == ".csv" else "html"
                if attachment.suffix == ".json":
                    subtype = "plain"
                msg.add_attachment(
                    data,
                    maintype=maintype,
                    subtype=subtype,
                    filename=attachment.name,
                )

        try:
            host = self._smtp_config.get("host", "localhost")
            port = self._smtp_config.get("port", 587)
            use_tls = self._smtp_config.get("use_tls", True)
            username = self._smtp_config.get("username")
            password = self._smtp_config.get("password")

            if use_tls:
                server = smtplib.SMTP(host, port)
                server.starttls()
            else:
                server = smtplib.SMTP(host, port)

            if username and password:
                server.login(username, password)
            server.send_message(msg)
            server.quit()
            logger.info("Email sent to {}", recipients)
            return True
        except Exception as exc:
            logger.error("Failed to send email: {}", exc)
            return False

    def _collect_report_data(
        self, report_type: str, as_of_date: date
    ) -> dict[str, Any]:
        """Collect data for a report type."""
        if report_type == "daily_digest":
            digest = self._query.get_daily_digest(as_of_date)
            return digest.model_dump()
        elif report_type == "gst_summary":
            rows = self._query.get_gst_summary(as_of_date, as_of_date)
            return {
                "data": rows,
                "from_date": str(as_of_date),
                "to_date": str(as_of_date),
            }
        elif report_type == "receivables":
            bills = self._query.get_receivables(overdue_only=False)
            return {"data": [b.model_dump() for b in bills]}
        elif report_type == "payables":
            bills = self._cache.get_outstanding_payables()
            return {"data": [b.model_dump() for b in bills]}
        elif report_type == "stock_summary":
            items = self._query.get_low_stock_items(
                threshold_quantity=Decimal("0")
            )
            return {
                "data": [
                    {"name": i.name, "quantity": str(i.closing_quantity)}
                    for i in items
                ]
            }
        elif report_type == "einvoice_summary":
            summary = self._query.get_einvoice_summary(as_of_date, as_of_date)
            return {"data": summary}
        else:
            return {"error": f"Unknown report type: {report_type}"}

    def _write_json(self, data: dict[str, Any], path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def _write_csv(self, data: dict[str, Any], path: Path) -> None:
        rows = data.get("data", [data])
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        if isinstance(rows, dict):
            rows = [rows]
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            fieldnames = list(rows[0].keys())
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow(
                        {
                            k: str(v) if not isinstance(v, str) else v
                            for k, v in row.items()
                        }
                    )

    def _write_html(
        self, report_type: str, data: dict[str, Any], path: Path
    ) -> None:
        rows = data.get("data", [data])
        title = report_type.replace("_", " ").title()
        html = f"<html><head><title>{title}</title></head><body>"
        html += f"<h1>{title} — {date.today()}</h1>"
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            html += "<table border='1'><thead><tr>"
            for key in rows[0]:
                html += f"<th>{key}</th>"
            html += "</tr></thead><tbody>"
            for row in rows:
                html += "<tr>"
                for key in rows[0]:
                    html += f"<td>{row.get(key, '')}</td>"
                html += "</tr>"
            html += "</tbody></table>"
        else:
            html += f"<pre>{json.dumps(data, indent=2, default=str)}</pre>"
        html += "</body></html>"
        path.write_text(html, encoding="utf-8")

    def _frequency_to_seconds(self, frequency: str) -> float:
        mapping = {"daily": 86400, "weekly": 604800, "monthly": 2592000}
        return float(mapping.get(frequency, 86400))

    def _is_due(self, schedule: dict[str, Any], now: datetime) -> bool:
        last_run = schedule.get("last_run")
        if last_run is None:
            return True
        try:
            last_dt = datetime.fromisoformat(str(last_run))
        except (ValueError, TypeError):
            return True
        freq = schedule.get("frequency", "daily")
        delta_map: dict[str, timedelta] = {
            "daily": timedelta(days=1),
            "weekly": timedelta(weeks=1),
            "monthly": timedelta(days=30),
        }
        delta = delta_map.get(freq, timedelta(days=1))
        return now - last_dt >= delta
