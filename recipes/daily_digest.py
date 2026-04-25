"""Daily Digest Recipe - Print a Rich-formatted business summary.

Connects to TallyPrime via tallybridge, fetches the daily digest,
and prints a formatted summary table to the console. Optionally
posts the summary to WhatsApp via the Cloud API.

Environment variables:
    TALLYBRIDGE_TALLY_HOST: Tally host (default: localhost)
    TALLYBRIDGE_TALLY_PORT: Tally port (default: 9000)
    TALLYBRIDGE_TALLY_COMPANY: Company name (optional)
    WA_PHONE_NUMBER_ID: WhatsApp Business phone number ID
    WA_TOKEN: WhatsApp Business access token
    WA_RECIPIENT_NUMBER: Recipient phone number (with country code)
"""

import os
import sys

from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.table import Table

import tallybridge
from tallybridge.exceptions import TallyConnectionError


class WhatsAppConfig(BaseSettings):
    wa_phone_number_id: str | None = None
    wa_token: str | None = None
    wa_recipient_number: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def is_configured(self) -> bool:
        return all([self.wa_phone_number_id, self.wa_token, self.wa_recipient_number])


def _build_digest_table(digest: tallybridge.DailyDigest) -> Table:
    table = Table(title=f"Daily Digest — {digest.digest_date.isoformat()}", show_lines=True)
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", justify="right", style="green")

    table.add_row("Company", digest.company)
    table.add_row("Total Sales", f"\u20b9{digest.total_sales:,.2f}")
    table.add_row("Total Purchases", f"\u20b9{digest.total_purchases:,.2f}")
    table.add_row("Cash Balance", f"\u20b9{digest.cash_balance:,.2f}")
    table.add_row("Bank Balance", f"\u20b9{digest.bank_balance:,.2f}")

    if digest.top_overdue_receivables:
        table.add_row(
            "Top Overdue",
            f"{len(digest.top_overdue_receivables)} bills, "
            f"max {digest.top_overdue_receivables[0].overdue_days} days overdue",
        )
    else:
        table.add_row("Top Overdue", "None")

    if digest.low_stock_items:
        table.add_row("Low Stock", ", ".join(digest.low_stock_items[:5]))
    else:
        table.add_row("Low Stock", "None")

    return table


def _post_to_whatsapp(text: str, config: WhatsAppConfig) -> None:
    import httpx

    if not config.is_configured:
        logger.warning("WhatsApp config incomplete — skipping post")
        return

    url = f"https://graph.facebook.com/v18.0/{config.wa_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {config.wa_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": config.wa_recipient_number,
        "type": "text",
        "text": {"body": text},
    }

    with httpx.Client(timeout=15.0) as client:
        try:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            logger.info("WhatsApp message sent successfully")
        except httpx.HTTPError as exc:
            logger.error("WhatsApp post failed: {}", exc)


def main() -> None:
    console = Console()
    wa_config = WhatsAppConfig()

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

    digest = q.get_daily_digest()
    table = _build_digest_table(digest)
    console.print(table)

    if wa_config.is_configured:
        lines = [
            f"Daily Digest — {digest.digest_date.isoformat()}",
            f"Sales: \u20b9{digest.total_sales:,.2f}",
            f"Purchases: \u20b9{digest.total_purchases:,.2f}",
            f"Cash: \u20b9{digest.cash_balance:,.2f}",
            f"Bank: \u20b9{digest.bank_balance:,.2f}",
        ]
        _post_to_whatsapp("\n".join(lines), wa_config)


if __name__ == "__main__":
    main()
