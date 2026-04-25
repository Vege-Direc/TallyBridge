"""GST Mismatch Alert - Flag invoices with missing GSTIN.

Fetches the GST summary and sales vouchers for the current month,
then checks for invoices above the threshold amount that are missing
a GSTIN on the party ledger. Prints an actionable report.

Environment variables:
    TALLYBRIDGE_TALLY_HOST: Tally host (default: localhost)
    TALLYBRIDGE_TALLY_PORT: Tally port (default: 9000)
    TALLYBRIDGE_TALLY_COMPANY: Company name (optional)
    GST_THRESHOLD: Invoice amount threshold for GSTIN check (default: 50000)
"""

import os
import sys
from datetime import date, timedelta
from decimal import Decimal

from loguru import logger
from rich.console import Console
from rich.table import Table

import tallybridge
from tallybridge.exceptions import TallyConnectionError


THRESHOLD_DEFAULT = Decimal("50000")


def _date_range_this_month() -> tuple[date, date]:
    today = date.today()
    from_date = today.replace(day=1)
    to_date = today
    return from_date, to_date


def _build_gst_summary_table(gst: dict[str, Decimal]) -> Table:
    table = Table(title="GST Summary", show_lines=True)
    table.add_column("Component", style="bold cyan")
    table.add_column("Amount", justify="right", style="green")

    for key, value in gst.items():
        label = key.replace("total_", "").replace("_", " ").title()
        table.add_row(label, f"\u20b9{value:,.2f}")

    return table


def _build_mismatch_table(
    mismatches: list[dict],
) -> Table:
    table = Table(title="Invoices Missing GSTIN (above threshold)", show_lines=True)
    table.add_column("Voucher No.", style="bold")
    table.add_column("Date")
    table.add_column("Party", style="cyan")
    table.add_column("Amount", justify="right", style="red")
    table.add_column("Issue", style="yellow")

    for m in mismatches:
        table.add_row(
            m["voucher_number"],
            m["date"].isoformat(),
            m["party"],
            f"\u20b9{m['amount']:,.2f}",
            m["issue"],
        )

    return table


def main() -> None:
    console = Console()
    threshold = Decimal(os.getenv("GST_THRESHOLD", str(THRESHOLD_DEFAULT)))

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

    from_date, to_date = _date_range_this_month()

    gst = q.get_gst_summary(from_date, to_date)
    console.print(_build_gst_summary_table(gst))

    sales = q.get_vouchers(voucher_type="Sales", from_date=from_date, to_date=to_date, limit=5000)

    mismatches: list[dict] = []
    for v in sales:
        if v.total_amount < threshold:
            continue
        if not v.party_gstin or not v.party_gstin.strip():
            mismatches.append({
                "voucher_number": v.voucher_number,
                "date": v.date,
                "party": v.party_ledger or "Unknown",
                "amount": v.total_amount,
                "issue": "Missing GSTIN",
            })

    if mismatches:
        console.print(_build_mismatch_table(mismatches))
        console.print(
            f"[bold yellow]Action required:[/bold yellow] "
            f"{len(mismatches)} invoice(s) above \u20b9{threshold:,.0f} "
            f"are missing GSTIN. Update party ledgers in Tally before filing."
        )
    else:
        console.print("[green]All invoices above threshold have GSTIN — no mismatches found.[/green]")


if __name__ == "__main__":
    main()
