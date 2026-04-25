"""HTTP connection to TallyPrime — see SPECS.md §4."""

import re

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from tallybridge.config import TallyBridgeConfig
from tallybridge.exceptions import TallyConnectionError, TallyDataError


class TallyConnection:
    def __init__(self, config: TallyBridgeConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(timeout=30.0)

    async def ping(self) -> bool:
        """Returns True if Tally responds, False otherwise. Never raises."""
        try:
            response = await self._client.post(
                self._config.tally_url,
                content=self._build_ping_xml().encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
            return response.status_code == 200
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.HTTPError):
            return False

    async def get_company_list(self) -> list[str]:
        """List all company names currently open in Tally.

        Raises:
            TallyConnectionError: If Tally is not running.
        """
        xml = self._build_collection_xml(
            "CompanyList", "Company", ["NAME"], company=None
        )
        response_xml = await self.post_xml(xml)
        companies: list[str] = []
        for match in re.finditer(r"<COMPANY[^>]*>\s*<NAME>([^<]+)</NAME>", response_xml):
            companies.append(match.group(1))
        return companies

    async def export_collection(
        self,
        collection_name: str,
        tally_type: str,
        fields: list[str],
        filter_expr: str | None = None,
        company: str | None = None,
    ) -> str:
        """Export a Tally collection and return raw XML string.

        Args:
            collection_name: Arbitrary name for this collection (used in XML).
            tally_type: Tally object type: Ledger, Voucher, StockItem, Group, etc.
            fields: List of Tally field names to fetch.
            filter_expr: TDL filter expression, e.g. "$ALTERID > 1000". None = no filter.
            company: Company name, or None for the active company.

        Raises:
            TallyConnectionError: Tally not running.
            TallyDataError: Tally returned LINEERROR.
        """
        xml = self._build_collection_xml(
            collection_name, tally_type, fields, filter_expr, company
        )
        return await self.post_xml(xml)

    async def get_alter_id_max(
        self, tally_type: str, company: str | None = None
    ) -> int:
        """Return current maximum AlterID for a Tally type. Returns 0 if none."""
        xml = self._build_collection_xml(
            f"MaxAlter_{tally_type}",
            tally_type,
            ["ALTERID"],
            company=company,
        )
        response_xml = await self.post_xml(xml)
        alter_ids = re.findall(r"<ALTERID>(\d+)</ALTERID>", response_xml)
        if not alter_ids:
            return 0
        return max(int(a) for a in alter_ids)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type(TallyConnectionError),
        reraise=True,
    )
    async def post_xml(self, xml_body: str) -> str:
        """POST UTF-8 XML to Tally, return UTF-16 decoded response string.

        Raises:
            TallyConnectionError: On connection refused.
            TallyDataError: Tally returned LINEERROR.
        """
        logger.debug("POSTing to {}: {} chars", self._config.tally_url, len(xml_body))
        try:
            response = await self._client.post(
                self._config.tally_url,
                content=xml_body.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            logger.warning("Tally connection failed: {}", exc)
            raise TallyConnectionError(
                f"Could not connect to Tally on {self._config.tally_host}:{self._config.tally_port}. "
                f"Is TallyPrime open? Enable: F1 > Settings > Connectivity > "
                f"TallyPrime acts as = Server, Port = {self._config.tally_port}"
            ) from exc

        decoded = response.content.decode("utf-16", errors="replace")
        logger.debug("Response: {} chars", len(decoded))

        if "<LINEERROR>" in decoded:
            error_match = re.search(r"<LINEERROR>([^<]+)</LINEERROR>", decoded)
            error_text = error_match.group(1) if error_match else "Unknown error"
            raise TallyDataError(
                f"Tally error: {error_text}",
                raw_response=decoded,
                error_text=error_text,
            )

        return decoded

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _build_ping_xml() -> str:
        return (
            "<ENVELOPE>"
            "<HEADER><VERSION>1</VERSION>"
            "<TALLYREQUEST>Export Data</TALLYREQUEST>"
            "<TYPE>Collection</TYPE><ID>Ping</ID></HEADER>"
            "<BODY><DESC><STATICVARIABLES>"
            "<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
            "</STATICVARIABLES>"
            "<TDL><TDLMESSAGE>"
            '<COLLECTION NAME="Ping" ISMODIFY="No">'
            "<TYPE>Company</TYPE><FETCH>NAME</FETCH>"
            "</COLLECTION>"
            "</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"
        )

    @staticmethod
    def _build_collection_xml(
        collection_name: str,
        tally_type: str,
        fields: list[str],
        filter_expr: str | None = None,
        company: str | None = None,
    ) -> str:
        fetch_tags = ",".join(fields)
        static_vars = "<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
        if company:
            static_vars += f"<SVCURRENTCOMPANY>{company}</SVCURRENTCOMPANY>"

        filter_section = ""
        if filter_expr:
            filter_section = f'<FILTER>AltFilter</FILTER>'
            filter_section += (
                f'<SYSTEM TYPE="Formulae" NAME="AltFilter">{filter_expr}</SYSTEM>'
            )

        return (
            "<ENVELOPE>"
            "<HEADER><VERSION>1</VERSION>"
            "<TALLYREQUEST>Export Data</TALLYREQUEST>"
            f"<TYPE>Collection</TYPE><ID>{collection_name}</ID></HEADER>"
            "<BODY><DESC><STATICVARIABLES>"
            f"{static_vars}"
            "</STATICVARIABLES>"
            "<TDL><TDLMESSAGE>"
            f'<COLLECTION NAME="{collection_name}" ISMODIFY="No">'
            f"<TYPE>{tally_type}</TYPE>"
            f"<FETCH>{fetch_tags}</FETCH>"
            f"{filter_section}"
            "</COLLECTION>"
            "</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"
        )
