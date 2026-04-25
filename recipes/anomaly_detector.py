"""Anomaly Detector - Flag suspicious transactions from the last 30 days.

Fetches vouchers from the past 30 days and flags:
1. Transactions exceeding 2x the daily average amount
2. Round-number payments that are exact multiples of 50,000
3. Empty narration on vouchers above 10,000

Environment variables:
    TALLYBRIDGE_TALLY_HOST: Tally host (default: localhost)
    TALLYBRIDGE_TALLY_PORT: Tally port (default: 9000)
    TALLYBRIDGE_TALLY_COMPANY: Company name (optional)
"""

import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from loguru import logger
from rich.console import Console
from rich.table import Table

import tallybridge
from tallybridge.exceptions import TallyConnectionError


MULTIPLE_THRESHOLD = Decimal("50000")
NARRATION_THRESHOLD = Decimal("10000")
AVERAGE_MULTIPLIER = 2


def _flag_high_value(
    vouchers: list[tallybridge.TallyVoucher],
) -> list[dict]:
    daily_totals: dict[str, Decimal] = defaultdict(Decimal)
    daily_counts: dict[str, int] = defaultdict(int)

    for v in vouchers:
        key = v.date.isoformat()
        daily_totals[key] += v.total_amount
        daily_counts[key] += 1

    overall_total = sum(daily_totals.values())
    overall_count = sum(daily_counts.values())
    if overall_count == 0:
        return []

    daily_avg = overall_total / overall_count
    threshold = daily_avg * AVERAGE_MULTIPLIER

    flagged: list[dict] = []
    for v in vouchers:
        if v.total_amount > threshold:
            flagged.append({
                "voucher_number": v.voucher_number,
                "date": v.date,
                "party": v.party_ledger or "N/A",
                "amount": v.total_amount,
                "type": v.voucher_type,
                "anomaly": f"Exceeds 2x daily avg (\u20b9{daily_avg:,.0f})",
            })

    return flagged


def _flag_round_multiples(
    vouchers: list[tallybridge.TallyVoucher],
) -> list[dict]:
    flagged: list[dict] = []
    for v in vouchers:
        if v.total_amount > 0 and MULTIPLE_THRESHOLD > 0:
            remainder = v.total_amount % MULTIPLE_THRESHOLD
            if remainder == 0 and v.total_amount >= MULTIPLE_THRESHOLD:
                flagged.append({
                    "voucher_number": v.voucher_number,
                    "date": v.date,
                    "party": v.party_ledger or "N/A",
                    "amount": v.total_amount,
                    "type": v.voucher_type,
                    "anomaly": f"Exact multiple of \u20b9{MULTIPLE_THRESHOLD:,.0f}",
                })

    return flagged


def _flag_empty_narration(
    vouchers: list[tallybridge.TallyVoucher],
) -> list[dict]:
    flagged: list[dict] = []
    for v in vouchers:
        if v.total_amount >= NARRATION_THRESHOLD:
            if not v.narration or not v.narration.strip():
                flagged.append({
                    "voucher_number": v.voucher_number,
                    "date": v.date,
                    "party": v.party_ledger or "N/A",
                    "amount": v.total_amount,
                    "type": v.voucher_type,
                    "anomaly": f"Empty narration on voucher > \u20b9{NARRATION_THRESHOLD:,.0f}",
                })

    return flagged


def _build_anomaly_table(title: str, anomalies: list[dict]) -> Table:
    table = Table(title=title, show_lines=True)
    table.add_column("Voucher No.", style="bold")
    table.add_column("Date")
    table.add_column("Party", style="cyan")
    table.add_column("Amount", justify="right", style="red")
    table.add_column("Type")
    table.add_column("Anomaly", style="yellow")

    for a in anomalies:
        table.add_row(
            a["voucher_number"],
            a["date"].isoformat(),
            a["party"],
            f"\u20b9{a['amount']:,.2f}",
            a["type"],
            a["anomaly"],
        )

    return table


def main() -> None:
    console = Console()

    try:
        q = tallybridge.connect(
            tally_host=os.getenv("TALLYBRIDGE_TALLY_HOST", "localhost"),
            tally_port=int(os.getenv("TALLYBRIDGE_TALLY_PORT", "9000")),
            company=os.getenv("TALLYBRIDGE_TALLY_COMPANY"),
        )
    except TallyConnectionError as exc:
        console.print(f"[bold red]Tally is not connected:[/bold red] {exc}")
        console.print("Please ensure TallyPrime is running with HTTP server enabled on port 9000.")
        sys.exit(0)

    to_date = date.today()
    from_date = to_date - timedelta(days=30)

    vouchers = q.get_vouchers(from_date=from_date, to_date=to_date, limit=10000)
    if not vouchers:
        console.print("[green]No vouchers found in the last 30 days.[/green]")
        return

    console.print(f"Analyzing {len(vouchers)} vouchers from {from_date.isoformat()} to {to_date.isoformat()}...")

    high_value = _flag_high_value(vouchers)
    round_multiples = _flag_round_multiples(vouchers)
    empty_narration = _flag_empty_narration(vouchers)

    total_anomalies = len(high_value) + len(round_multiples) + len(empty_narration)

    if total_anomalies == 0:
        console.print("[green]No anomalies detected in the last 30 days.[/green]")
        return

    if high_value:
        console.print(_build_anomaly_table("High-Value Transactions (2x daily average)", high_value))

    if round_multiples:
        console.print(_build_anomaly_table("Round-Number Multiples (\u20b950,000)", round_multiples))

    if empty_narration:
        console.print(_build_anomaly_table("Empty Narration (>\u20b910,000)", empty_narration))

    console.print(
        f"[bold yellow]{total_anomalies} anomaly(ies) detected.[/bold yellow] "
        "Review flagged transactions for potential errors or irregularities."
    )


if __name__ == "__main__":
    main()
