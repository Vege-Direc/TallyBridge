"""HTTP connection to TallyPrime — see SPECS.md §4."""

import base64
import html
import json
import re
from typing import TYPE_CHECKING, Any, Union

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from tallybridge.config import TallyBridgeConfig
from tallybridge.exceptions import TallyConnectionError, TallyDataError

if TYPE_CHECKING:
    from tallybridge.models.report import (
        GSTR1Result,
        GSTR2AClaim,
        GSTR3BResult,
        GSTR9Result,
        ImportResult,
        TallyReport,
    )
    from tallybridge.version import TallyProduct


class TallyConnection:
    _detected_version: "TallyProduct | None"

    def __init__(self, config: TallyBridgeConfig) -> None:
        self._config = config
        self._detected_version = None
        transport = httpx.AsyncHTTPTransport(retries=3)
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        timeout = httpx.Timeout(30.0, connect=10.0, read=60.0, write=10.0, pool=5.0)
        self._client = httpx.AsyncClient(
            transport=transport,
            limits=limits,
            timeout=timeout,
        )

    async def ping(self) -> bool:
        """Returns True if Tally responds, False otherwise. Never raises."""
        try:
            response = await self._client.post(
                self._config.tally_url,
                content=self._build_ping_xml().encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
            return response.status_code == 200
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.HTTPError,
        ):
            return False

    async def detect_version(self) -> "TallyProduct":
        """Detect the Tally product version and cache it.

        Calls ``detect_tally_version()`` which queries Tally for
        its version string. The result is cached on
        ``self._detected_version`` and the capability set is logged.

        Returns:
            The detected ``TallyProduct`` enum value.
        """
        from tallybridge.version import detect_tally_version

        product = await detect_tally_version(self)
        caps = product.capabilities()
        logger.info(
            "Tally version: {} | Capabilities: {}",
            product.display_name,
            ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in caps.items()),
        )
        return product

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
        for match in re.finditer(
            r"<COMPANY[^>]*>\s*<NAME>([^<]+)</NAME>", response_xml
        ):
            companies.append(match.group(1))
        return companies

    async def export_collection(
        self,
        collection_name: str,
        tally_type: str,
        fields: list[str],
        filter_expr: str | None = None,
        company: str | None = None,
    ) -> str | dict[str, Any]:
        """Export a Tally collection. Returns XML string or JSON dict."""
        fmt = self._get_export_format()
        if fmt == "json":
            headers, body = self._build_collection_json(
                collection_name, tally_type, fields, filter_expr, company
            )
            return await self.post_json(headers, body)
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
        retry=retry_if_exception_type((httpx.ReadTimeout, TallyDataError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
        before_sleep=lambda rs: logger.warning(
            "Retrying post_xml (attempt {}): {}",
            rs.attempt_number,
            rs.outcome.exception() if rs.outcome else "unknown",
        ),
    )
    async def post_xml(self, xml_body: str) -> str:
        """POST XML to Tally, return decoded response string.

        Request and response encoding are aligned per config:
        - utf-8: Send UTF-8, decode response as UTF-8 (default, simpler)
        - utf-16: Send UTF-16LE, decode response as UTF-16LE (for ₹/€ symbols)

        Tally mirrors the request encoding in its response.

        Raises:
            TallyConnectionError: On connection refused.
            TallyDataError: Tally returned EXCEPTION, STATUS -1, or LINEERROR.
        """
        encoding = self._config.tally_encoding
        if encoding == "utf-16":
            content_type = "text/xml; charset=utf-16"
            encoded_body = xml_body.encode("utf-16-le")
            response_encoding = "utf-16"
        else:
            content_type = "text/xml; charset=utf-8"
            encoded_body = xml_body.encode("utf-8")
            response_encoding = "utf-8"

        logger.debug(
            "POSTing to {}: {} chars (encoding={})",
            self._config.tally_url,
            len(xml_body),
            encoding,
        )
        try:
            response = await self._client.post(
                self._config.tally_url,
                content=encoded_body,
                headers={"Content-Type": content_type},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            logger.warning("Tally connection failed: {}", exc)
            timeout_hint = ""
            if isinstance(exc, httpx.ReadTimeout):
                timeout_hint = (
                    " Read timeout is 60s. "
                    "Try reducing VOUCHER_BATCH_SIZE if syncing large datasets."
                )
            raise TallyConnectionError(
                f"Could not connect to Tally on "
                f"{self._config.tally_host}:{self._config.tally_port}. "
                f"Is TallyPrime open? Enable: F1 > Settings > Connectivity > "
                f"TallyPrime acts as = Server, "
                f"Port = {self._config.tally_port}.{timeout_hint}"
            ) from exc

        decoded = response.content.decode(response_encoding, errors="replace")
        logger.debug("Response: {} chars", len(decoded))

        if decoded.startswith("<EXCEPTION>"):
            error_match = re.search(r"<EXCEPTION>(.+?)</EXCEPTION>", decoded)
            error_text = (
                error_match.group(1) if error_match else "Unknown Tally exception"
            )
            raise TallyDataError(
                f"Tally exception: {error_text}",
                raw_response=decoded,
                error_text=error_text,
            )

        # NOTE on STATUS semantics: Official TallyHelp docs say
        # STATUS=0 means failure, but observed TallyPrime behavior
        # returns STATUS=0 for empty collections (no data).
        # STATUS=-1 indicates an actual error. STATUS=1 indicates success.
        # When strict_status is True (config), STATUS=0 is treated as error.
        # See: https://help.tallysolutions.com/integrate-with-tallyprime/
        status_match = re.search(r"<STATUS>(-?\d+)</STATUS>", decoded)
        if status_match:
            status_val = int(status_match.group(1))
            if status_val == -1:
                raise TallyDataError(
                    "Tally returned STATUS -1 (error)",
                    raw_response=decoded,
                    error_text=f"STATUS={status_val}",
                )
            if status_val == 0:
                logger.debug("Tally returned STATUS 0 — empty collection or no data")
                if self._config.strict_status:
                    raise TallyDataError(
                        "Tally returned STATUS 0 (treated as error in strict mode)",
                        raw_response=decoded,
                        error_text=f"STATUS={status_val}",
                    )

        if "<LINEERROR>" in decoded:
            error_match = re.search(r"<LINEERROR>([^<]+)</LINEERROR>", decoded)
            error_text = error_match.group(1) if error_match else "Unknown error"
            raise TallyDataError(
                f"Tally error: {error_text}",
                raw_response=decoded,
                error_text=error_text,
            )

        return decoded

    async def export_object(
        self,
        tally_type: str,
        name: str | None = None,
        guid: str | None = None,
        company: str | None = None,
        parse: bool = False,
    ) -> Union[str, dict[str, Any], list[Any]]:
        """Export a single Tally object by Name or GUID using TYPE=Object."""
        if not name and not guid:
            raise ValueError("export_object requires either 'name' or 'guid'")

        fmt = self._get_export_format()
        raw_json: dict[str, Any] | None = None
        raw_xml: str | None = None

        if fmt == "json":
            supports_b64 = (
                self._detected_version is not None
                and self._detected_version.supports_base64_encoding
            )
            headers, body = self._build_object_json(
                tally_type, name, guid, company, supports_base64=supports_b64
            )
            raw_json = await self.post_json(headers, body)
        else:
            xml = self._build_object_xml(tally_type, name, guid, company)
            raw_xml = await self.post_xml(xml)

        if not parse:
            return raw_json if raw_json is not None else raw_xml  # type: ignore[return-value]

        type_lower = tally_type.lower().replace(" ", "")

        if raw_json is not None:
            from tallybridge.parser import TallyJSONParser

            json_parser = TallyJSONParser()
            parse_json_map: dict[str, Any] = {
                "ledger": json_parser.parse_ledgers_json,
                "ledgers": json_parser.parse_ledgers_json,
                "group": json_parser.parse_groups_json,
                "groups": json_parser.parse_groups_json,
                "stockitem": json_parser.parse_stock_items_json,
                "stockitems": json_parser.parse_stock_items_json,
                "stockgroup": json_parser.parse_stock_groups_json,
                "stockgroups": json_parser.parse_stock_groups_json,
                "voucher": json_parser.parse_vouchers_json,
                "vouchers": json_parser.parse_vouchers_json,
                "unit": json_parser.parse_units_json,
                "units": json_parser.parse_units_json,
                "vouchertype": json_parser.parse_voucher_types_json,
                "vouchertypes": json_parser.parse_voucher_types_json,
                "costcenter": json_parser.parse_cost_centers_json,
                "costcentres": json_parser.parse_cost_centers_json,
                "costcentre": json_parser.parse_cost_centers_json,
            }
            parse_fn = parse_json_map.get(type_lower)
            if parse_fn is not None:
                result: list[Any] = parse_fn(raw_json)
                return result
            logger.warning(
                "Unknown tally_type '{}' for JSON parsing, returning raw dict",
                tally_type,
            )
            return [raw_json]

        from tallybridge.parser import TallyXMLParser

        xml_parser = TallyXMLParser()
        parse_xml_map: dict[str, Any] = {
            "ledger": xml_parser.parse_ledgers,
            "ledgers": xml_parser.parse_ledgers,
            "group": xml_parser.parse_groups,
            "groups": xml_parser.parse_groups,
            "stockitem": xml_parser.parse_stock_items,
            "stockitems": xml_parser.parse_stock_items,
            "stockgroup": xml_parser.parse_stock_groups,
            "stockgroups": xml_parser.parse_stock_groups,
            "voucher": xml_parser.parse_vouchers,
            "vouchers": xml_parser.parse_vouchers,
            "unit": xml_parser.parse_units,
            "units": xml_parser.parse_units,
            "vouchertype": xml_parser.parse_voucher_types,
            "vouchertypes": xml_parser.parse_voucher_types,
            "costcenter": xml_parser.parse_cost_centers,
            "costcentres": xml_parser.parse_cost_centers,
            "costcentre": xml_parser.parse_cost_centers,
            "godown": xml_parser.parse_stock_groups,
            "godowns": xml_parser.parse_stock_groups,
        }
        parse_fn = parse_xml_map.get(type_lower)
        if parse_fn is not None and raw_xml is not None:
            xml_result: list[Any] = parse_fn(raw_xml)
            return xml_result
        logger.warning(
            "Unknown tally_type '{}' for parsing, returning raw XML",
            tally_type,
        )
        return [raw_xml]

    async def fetch_report(
        self,
        report_name: str,
        from_date: str | None = None,
        to_date: str | None = None,
        company: str | None = None,
        parse: bool = False,
    ) -> "Union[str, dict[str, Any], TallyReport]":
        """Fetch a computed Tally report using TYPE=Data."""
        fmt = self._get_export_format()
        raw_json: dict[str, Any] | None = None
        raw_xml: str | None = None

        if fmt == "json":
            headers, body = self._build_report_json(
                report_name, from_date, to_date, company
            )
            raw_json = await self.post_json(headers, body)
        else:
            xml = self._build_report_xml(report_name, from_date, to_date, company)
            raw_xml = await self.post_xml(xml)

        if not parse:
            return raw_json if raw_json is not None else raw_xml  # type: ignore[return-value]

        from datetime import datetime

        parsed_from = (
            datetime.strptime(from_date, "%Y%m%d").date() if from_date else None
        )
        parsed_to = datetime.strptime(to_date, "%Y%m%d").date() if to_date else None

        if raw_json is not None:
            from tallybridge.parser import TallyJSONParser

            return TallyJSONParser.parse_report_json(
                raw_json,
                report_name=report_name,
                from_date=parsed_from,
                to_date=parsed_to,
            )

        from tallybridge.parser import TallyXMLParser

        return TallyXMLParser.parse_report(
            raw_xml or "",
            report_name=report_name,
            from_date=parsed_from,
            to_date=parsed_to,
        )

    async def fetch_gstr3b(
        self,
        from_date: str,
        to_date: str,
        company: str | None = None,
    ) -> "GSTR3BResult":
        """Fetch GSTR-3B return data from TallyPrime.

        Uses the TYPE=Data report pattern with report name ``GSTR 3B``.
        Requires TallyPrime with GST features (4.0+ for Connected GST).
        The response contains GST return sections matching the portal format.

        Args:
            from_date: Start date in ``YYYYMMDD`` format.
            to_date: End date in ``YYYYMMDD`` format.
            company: Company name (uses detected company if None).

        Returns:
            GSTR3BResult with parsed sections or raw response on parse failure.
        """
        from tallybridge.models.report import GSTR3BResult

        raw = await self.fetch_report(
            "GSTR 3B",
            from_date=from_date,
            to_date=to_date,
            company=company,
        )

        raw_str: str = ""
        if isinstance(raw, dict):
            import json

            raw_str = json.dumps(raw)
        elif isinstance(raw, str):
            raw_str = raw

        from datetime import datetime

        parsed_from = datetime.strptime(from_date, "%Y%m%d").date()
        parsed_to = datetime.strptime(to_date, "%Y%m%d").date()

        if isinstance(raw, dict):
            from tallybridge.parser import TallyJSONParser

            sections = TallyJSONParser.parse_gstr3b_json(raw)
        elif isinstance(raw, str):
            from tallybridge.parser import TallyXMLParser as _XMLParser

            sections = _XMLParser.parse_gstr3b(raw)
        else:
            sections = []

        return GSTR3BResult(
            from_date=parsed_from,
            to_date=parsed_to,
            sections=sections,
            raw_response=raw_str,
        )

    async def fetch_gstr1(
        self,
        from_date: str,
        to_date: str,
        company: str | None = None,
    ) -> "GSTR1Result":
        """Fetch GSTR-1 outward supply data from TallyPrime.

        Uses the TYPE=Data report pattern with report name ``GSTR 1``.
        Requires TallyPrime with GST features (4.0+ for Connected GST).
        The response contains invoice-level outward supply details matching
        the GST portal format.

        Args:
            from_date: Start date in ``YYYYMMDD`` format.
            to_date: End date in ``YYYYMMDD`` format.
            company: Company name (uses detected company if None).

        Returns:
            GSTR1Result with parsed sections or raw response on parse failure.
        """
        from tallybridge.models.report import GSTR1Result

        raw = await self.fetch_report(
            "GSTR 1",
            from_date=from_date,
            to_date=to_date,
            company=company,
        )

        raw_str: str = ""
        if isinstance(raw, dict):
            import json

            raw_str = json.dumps(raw)
        elif isinstance(raw, str):
            raw_str = raw

        from datetime import datetime

        parsed_from = datetime.strptime(from_date, "%Y%m%d").date()
        parsed_to = datetime.strptime(to_date, "%Y%m%d").date()

        if isinstance(raw, dict):
            from tallybridge.parser import TallyJSONParser

            sections = TallyJSONParser.parse_gstr1_json(raw)
        elif isinstance(raw, str):
            from tallybridge.parser import TallyXMLParser as _XMLParser

            sections = _XMLParser.parse_gstr1(raw)
        else:
            sections = []

        return GSTR1Result(
            from_date=parsed_from,
            to_date=parsed_to,
            sections=sections,
            raw_response=raw_str,
        )

    async def fetch_gstr2a(
        self,
        from_date: str,
        to_date: str,
        company: str | None = None,
    ) -> "list[GSTR2AClaim]":
        """Fetch GSTR-2A auto-populated inward supply data from TallyPrime.

        Uses the TYPE=Data report pattern with report name ``GSTR 2A``.
        Requires TallyPrime with GST features and Connected GST enabled.
        The response contains supplier-wise ITC claim data from the GST portal.

        Args:
            from_date: Start date in ``YYYYMMDD`` format.
            to_date: End date in ``YYYYMMDD`` format.
            company: Company name (uses detected company if None).

        Returns:
            List of GSTR2AClaim objects parsed from the Tally response.
        """
        raw = await self.fetch_report(
            "GSTR 2A",
            from_date=from_date,
            to_date=to_date,
            company=company,
        )

        if isinstance(raw, dict):
            from tallybridge.parser import TallyJSONParser

            return TallyJSONParser.parse_gstr2a_json(raw)
        elif isinstance(raw, str):
            from tallybridge.parser import TallyXMLParser as _XMLParser

            return _XMLParser.parse_gstr2a(raw)
        else:
            return []

    async def fetch_gstr9(
        self,
        from_date: str,
        to_date: str,
        company: str | None = None,
    ) -> "GSTR9Result":
        """Fetch GSTR-9 annual return data from TallyPrime.

        Uses the TYPE=Data report pattern with report name ``GSTR 9``.
        Requires TallyPrime with GST features. The response contains
        annual return sections matching the GST portal format.

        Args:
            from_date: Start date in ``YYYYMMDD`` format.
            to_date: End date in ``YYYYMMDD`` format.
            company: Company name (uses detected company if None).

        Returns:
            GSTR9Result with parsed sections or raw response on parse failure.
        """
        from tallybridge.models.report import GSTR9Result

        raw = await self.fetch_report(
            "GSTR 9",
            from_date=from_date,
            to_date=to_date,
            company=company,
        )

        raw_str: str = ""
        if isinstance(raw, dict):
            import json

            raw_str = json.dumps(raw)
        elif isinstance(raw, str):
            raw_str = raw

        from datetime import datetime

        parsed_from = datetime.strptime(from_date, "%Y%m%d").date()
        parsed_to = datetime.strptime(to_date, "%Y%m%d").date()

        if isinstance(raw, dict):
            from tallybridge.parser import TallyJSONParser

            sections = TallyJSONParser.parse_gstr9_json(raw)
        elif isinstance(raw, str):
            from tallybridge.parser import TallyXMLParser as _XMLParser

            sections = _XMLParser.parse_gstr9(raw)
        else:
            sections = []

        return GSTR9Result(
            from_date=parsed_from,
            to_date=parsed_to,
            sections=sections,
            raw_response=raw_str,
        )

    @staticmethod
    def encode_name_base64(name: str) -> str:
        """Encode a multilingual entity name to base64 for TallyPrime 7.0+."""
        return base64.b64encode(name.encode("utf-8")).decode("ascii")

    def _require_capability(self, capability: str) -> None:
        """Raise TallyConnectionError if a required capability is unsupported."""
        if self._detected_version is None:
            return
        cap_map = {
            "json_api": self._detected_version.supports_json_api,
            "base64_encoding": self._detected_version.supports_base64_encoding,
            "tally_drive": self._detected_version.supports_tally_drive,
        }
        supported = cap_map.get(capability)
        if supported is False:
            raise TallyConnectionError(
                f"'{capability}' requires TallyPrime 7.0+ but detected "
                f"version is {self._detected_version.display_name}. "
                f"Set TALLYBRIDGE_TALLY_EXPORT_FORMAT=xml to use XML mode."
            )

    def _get_export_format(self) -> str:
        """Return 'json' or 'xml' based on config and detected version."""
        fmt = self._config.tally_export_format
        if fmt == "xml":
            return "xml"
        if fmt == "json":
            return "json"
        if (
            self._detected_version is not None
            and self._detected_version.supports_json_api
        ):
            return "json"
        return "xml"

    @retry(
        retry=retry_if_exception_type((httpx.ReadTimeout, TallyDataError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
        before_sleep=lambda rs: logger.warning(
            "Retrying post_json (attempt {}): {}",
            rs.attempt_number,
            rs.outcome.exception() if rs.outcome else "unknown",
        ),
    )
    async def post_json(
        self, headers: dict[str, str], body: dict[str, Any]
    ) -> dict[str, Any]:
        """POST JSON to TallyPrime 7.0+, return parsed response dict.

        TallyPrime 7.0+ differentiates JSON from XML by the Content-Type
        header. JSON requests use custom HTTP headers (version, tallyrequest,
        type, id, etc.) and a JSON body with static_variables/fetchlist.
        """
        request_headers = {
            "Content-Type": "application/json",
            "version": "1",
        }
        request_headers.update(headers)

        encoded_body = json.dumps(body).encode("utf-8")
        logger.debug(
            "POSTing JSON to {}: {} bytes",
            self._config.tally_url,
            len(encoded_body),
        )
        try:
            response = await self._client.post(
                self._config.tally_url,
                content=encoded_body,
                headers=request_headers,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            logger.warning("Tally JSON connection failed: {}", exc)
            timeout_hint = ""
            if isinstance(exc, httpx.ReadTimeout):
                timeout_hint = " Read timeout. Try reducing VOUCHER_BATCH_SIZE."
            raise TallyConnectionError(
                f"Could not connect to Tally on "
                f"{self._config.tally_host}:{self._config.tally_port}. "
                f"Is TallyPrime open? Enable: F1 > Settings > Connectivity > "
                f"TallyPrime acts as = Server, "
                f"Port = {self._config.tally_port}.{timeout_hint}"
            ) from exc

        decoded = response.content.decode("utf-8", errors="replace")
        logger.debug("JSON Response: {} chars", len(decoded))

        try:
            data = json.loads(decoded)
        except (json.JSONDecodeError, ValueError) as exc:
            raise TallyDataError(
                f"Tally returned invalid JSON: {exc}",
                raw_response=decoded,
                error_text=str(exc),
            ) from exc

        status_val = data.get("status")
        if status_val is not None:
            status_int = int(status_val) if isinstance(status_val, str) else status_val
            if status_int == -1:
                raise TallyDataError(
                    "Tally JSON returned status -1 (error)",
                    raw_response=decoded,
                    error_text=f"status={status_int}",
                )
            if status_int == 0:
                logger.debug(
                    "Tally JSON returned status 0 — empty collection or no data"
                )
                if self._config.strict_status:
                    raise TallyDataError(
                        "Tally JSON returned status 0 "
                        "(treated as error in strict mode)",
                        raw_response=decoded,
                        error_text=f"status={status_int}",
                    )

        error_text = data.get("error") or data.get("lineerror")
        if error_text:
            raise TallyDataError(
                f"Tally JSON error: {error_text}",
                raw_response=decoded,
                error_text=str(error_text),
            )

        return dict(data)

    async def import_masters(
        self,
        xml_data: str,
        company: str | None = None,
        action: str = "Create",
    ) -> "ImportResult":
        """Import master data (ledgers, groups, stock items, etc.) into TallyPrime.

        Sends an XML import request via ``TALLYREQUEST=Import Data``.
        Requires ``TALLYBRIDGE_ALLOW_WRITES=true`` in the environment.

        Args:
            xml_data: Tally-formatted XML containing one or more master objects
                (e.g. ``<LEDGER>`` elements).
            company: Target company name. If ``None``, uses the active company.
            action: Import action — ``"Create"``, ``"Alter"``, ``"Delete"``.
                Defaults to ``"Create"``.

        Returns:
            An ``ImportResult`` with created/altered/deleted/error counts.

        Raises:
            TallyConnectionError: If ``allow_writes`` is ``False`` or Tally is
                unreachable.
            TallyDataError: If Tally rejects the import.
        """
        self._check_writes_allowed()

        envelope = (
            "<ENVELOPE>"
            "<HEADER><VERSION>1</VERSION>"
            "<TALLYREQUEST>Import Data</TALLYREQUEST>"
            "</HEADER>"
            "<BODY><IMPORTDATA>"
            "<REQUESTDESC><REPORTNAME>All Masters</REPORTNAME></REQUESTDESC>"
            f"<REQUESTDATA><TALLYMESSAGE>"
            f"{xml_data}"
            f"</TALLYMESSAGE></REQUESTDATA>"
            "</IMPORTDATA></BODY></ENVELOPE>"
        )

        response = await self.post_xml(envelope)
        return self._parse_import_response_xml(response)

    async def import_vouchers(
        self,
        xml_data: str,
        company: str | None = None,
        action: str = "Create",
    ) -> "ImportResult":
        """Import voucher data (sales, purchases, receipts, etc.) into TallyPrime.

        Sends an XML import request via ``TALLYREQUEST=Import Data``.
        Requires ``TALLYBRIDGE_ALLOW_WRITES=true`` in the environment.

        Args:
            xml_data: Tally-formatted XML containing one or more ``<VOUCHER>``
                elements.
            company: Target company name. If ``None``, uses the active company.
            action: Import action — ``"Create"``, ``"Alter"``, ``"Delete"``.
                Defaults to ``"Create"``.

        Returns:
            An ``ImportResult`` with created/altered/deleted/error counts.
        """
        self._check_writes_allowed()

        envelope = (
            "<ENVELOPE>"
            "<HEADER><VERSION>1</VERSION>"
            "<TALLYREQUEST>Import Data</TALLYREQUEST>"
            "</HEADER>"
            "<BODY><IMPORTDATA>"
            "<REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME></REQUESTDESC>"
            f"<REQUESTDATA><TALLYMESSAGE>"
            f"{xml_data}"
            f"</TALLYMESSAGE></REQUESTDATA>"
            "</IMPORTDATA></BODY></ENVELOPE>"
        )

        response = await self.post_xml(envelope)
        return self._parse_import_response_xml(response)

    async def import_masters_json(
        self,
        tally_message: dict[str, Any],
        company: str | None = None,
        detailed_response: bool = True,
    ) -> "ImportResult":
        """Import master data using JSON/JSONEx format (TallyPrime 7.0+).

        Args:
            tally_message: The ``tallymessage`` dict containing master object
                data in Tally's native JSON structure.
            company: Target company name.
            detailed_response: If ``True``, include the ``detailed-response``
                header for object creation/alteration counts.

        Returns:
            An ``ImportResult`` with created/altered/deleted/error counts.
        """
        self._check_writes_allowed()
        self._require_capability("json_api")

        headers, body = self._build_import_json(
            import_id="All Masters",
            tally_message=tally_message,
            company=company,
            import_format="JSONEx",
            detailed_response=detailed_response,
        )
        raw = await self.post_json(headers, body)
        return self._parse_import_response_json(raw)

    async def import_vouchers_json(
        self,
        tally_message: dict[str, Any],
        company: str | None = None,
        detailed_response: bool = True,
    ) -> "ImportResult":
        """Import voucher data using JSON/JSONEx format (TallyPrime 7.0+).

        Args:
            tally_message: The ``tallymessage`` dict containing voucher object
                data in Tally's native JSON structure.
            company: Target company name.
            detailed_response: If ``True``, include the ``detailed-response``
                header for object creation/alteration counts.

        Returns:
            An ``ImportResult`` with created/altered/deleted/error counts.
        """
        self._check_writes_allowed()
        self._require_capability("json_api")

        headers, body = self._build_import_json(
            import_id="Vouchers",
            tally_message=tally_message,
            company=company,
            import_format="JSONEx",
            detailed_response=detailed_response,
        )
        raw = await self.post_json(headers, body)
        return self._parse_import_response_json(raw)

    def _check_writes_allowed(self) -> None:
        """Raise TallyConnectionError if writes are not enabled."""
        if not self._config.allow_writes:
            raise TallyConnectionError(
                "Import operations require TALLYBRIDGE_ALLOW_WRITES=true. "
                "Set this environment variable to enable write-back to TallyPrime."
            )

    @staticmethod
    def _build_import_xml(
        report_name: str,
        xml_data: str,
        company: str | None = None,
    ) -> str:
        """Build XML envelope for a TallyPrime import request."""
        safe_company = html.escape(company, quote=True) if company else ""
        static_vars = ""
        if safe_company:
            static_vars = f"<SVCURRENTCOMPANY>{safe_company}</SVCURRENTCOMPANY>"
        return (
            "<ENVELOPE>"
            "<HEADER><VERSION>1</VERSION>"
            "<TALLYREQUEST>Import Data</TALLYREQUEST>"
            "</HEADER>"
            "<BODY><IMPORTDATA>"
            f"<REQUESTDESC><REPORTNAME>{html.escape(report_name, quote=True)}"
            f"</REPORTNAME></REQUESTDESC>"
            f"<REQUESTDATA><TALLYMESSAGE>"
            f"{xml_data}"
            f"</TALLYMESSAGE></REQUESTDATA>"
            f"{static_vars}"
            "</IMPORTDATA></BODY></ENVELOPE>"
        )

    @staticmethod
    def _build_import_json(
        import_id: str,
        tally_message: dict[str, Any],
        company: str | None = None,
        import_format: str = "JSONEx",
        detailed_response: bool = True,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Build HTTP headers and JSON body for a TallyPrime 7.0+ import.

        Returns (headers_dict, body_dict) suitable for post_json().
        """
        headers: dict[str, str] = {
            "tallyrequest": "Import",
            "type": "Data",
            "id": import_id,
        }
        if detailed_response:
            headers["detailed-response"] = "Yes"

        sv_format_key = (
            "svmstimportformat" if import_id == "All Masters" else "svvchimportformat"
        )
        static_variables: dict[str, str] = {
            sv_format_key: import_format,
        }
        if company:
            static_variables["svcurrentcompany"] = company

        body: dict[str, Any] = {
            "static_variables": static_variables,
            "tallymessage": tally_message,
        }

        return headers, body

    @staticmethod
    def _parse_import_response_xml(response: str) -> "ImportResult":
        """Parse an XML import response into an ImportResult."""
        from tallybridge.models.report import ImportResult

        created = 0
        altered = 0
        deleted = 0
        errors = 0
        error_messages: list[str] = []

        created_match = re.search(r"<CREATED>(\d+)</CREATED>", response, re.IGNORECASE)
        altered_match = re.search(r"<ALTERED>(\d+)</ALTERED>", response, re.IGNORECASE)
        deleted_match = re.search(r"<DELETED>(\d+)</DELETED>", response, re.IGNORECASE)
        errors_match = re.search(r"<ERRORS>(\d+)</ERRORS>", response, re.IGNORECASE)

        if created_match:
            created = int(created_match.group(1))
        if altered_match:
            altered = int(altered_match.group(1))
        if deleted_match:
            deleted = int(deleted_match.group(1))
        if errors_match:
            errors = int(errors_match.group(1))

        line_error_matches = re.findall(
            r"<LINEERROR>([^<]+)</LINEERROR>", response, re.IGNORECASE
        )
        error_messages.extend(line_error_matches)

        status_match = re.search(r"<STATUS>(-?\d+)</STATUS>", response)
        success = True
        if status_match:
            status_val = int(status_match.group(1))
            success = status_val >= 0

        if not success and not error_messages:
            status_val_str = status_match.group(1) if status_match else "unknown"
            error_messages.append(f"Import failed with STATUS={status_val_str}")

        return ImportResult(
            success=success and errors == 0,
            created=created,
            altered=altered,
            deleted=deleted,
            errors=errors,
            error_messages=error_messages,
            raw_response=response,
        )

    @staticmethod
    def _parse_import_response_json(data: dict[str, Any]) -> "ImportResult":
        """Parse a JSON import response into an ImportResult."""
        from tallybridge.models.report import ImportResult

        created = 0
        altered = 0
        deleted = 0
        errors = 0
        error_messages: list[str] = []

        cmp_info = data.get("cmp_info", {})
        if isinstance(cmp_info, dict):
            created = int(cmp_info.get("created", 0) or 0)
            altered = int(cmp_info.get("altered", 0) or 0)
            deleted = int(cmp_info.get("deleted", 0) or 0)
            errors = int(cmp_info.get("errors", 0) or 0)

        status_val = data.get("status")
        success = True
        if status_val is not None:
            status_int = int(status_val) if isinstance(status_val, str) else status_val
            success = status_int >= 0

        tally_msg = data.get("tallymessage", [])
        if isinstance(tally_msg, list):
            for item in tally_msg:
                if isinstance(item, dict):
                    err = item.get("lineerror") or item.get("error")
                    if err:
                        error_messages.append(str(err))

        if not success and not error_messages:
            error_messages.append(f"Import failed with status={status_val}")

        return ImportResult(
            success=success and errors == 0,
            created=created,
            altered=altered,
            deleted=deleted,
            errors=errors,
            error_messages=error_messages,
            raw_response=json.dumps(data),
        )

    @staticmethod
    def build_ledger_xml(
        name: str,
        parent_group: str = "Sundry Debtors",
        opening_balance: str = "0",
        action: str = "Create",
    ) -> str:
        """Build a ``<LEDGER>`` XML fragment for import.

        Args:
            name: Ledger name.
            parent_group: Parent group name (e.g. ``"Sundry Debtors"``).
            opening_balance: Opening balance string (e.g. ``"5000"``).
            action: Import action — ``"Create"``, ``"Alter"``, ``"Delete"``.

        Returns:
            XML string fragment suitable for ``import_masters()``.
        """
        safe_name = html.escape(name, quote=True)
        safe_parent = html.escape(parent_group, quote=True)
        safe_action = html.escape(action, quote=True)
        safe_balance = html.escape(opening_balance, quote=True)
        return (
            f'<LEDGER NAME="{safe_name}" ACTION="{safe_action}">'
            f"<NAME.LIST><NAME>{safe_name}</NAME></NAME.LIST>"
            f"<PARENT>{safe_parent}</PARENT>"
            f"<OPENINGBALANCE>{safe_balance}</OPENINGBALANCE>"
            f"</LEDGER>"
        )

    @staticmethod
    def build_voucher_xml(
        voucher_type: str,
        date: str,
        ledger_entries: list[dict[str, str]],
        narration: str | None = None,
        voucher_number: str | None = None,
        party_ledger: str | None = None,
        action: str = "Create",
    ) -> str:
        """Build a ``<VOUCHER>`` XML fragment for import.

        Args:
            voucher_type: Voucher type name (e.g. ``"Sales"``, ``"Payment"``).
            date: Date in YYYYMMDD format.
            ledger_entries: List of dicts with keys ``"ledger_name"`` and
                ``"amount"`` (positive=Dr, negative=Cr).
            narration: Optional narration text.
            voucher_number: Optional voucher number.
            party_ledger: Optional party ledger name.
            action: Import action — ``"Create"``, ``"Alter"``, ``"Delete"``.

        Returns:
            XML string fragment suitable for ``import_vouchers()``.
        """
        safe_type = html.escape(voucher_type, quote=True)
        safe_action = html.escape(action, quote=True)
        safe_date = html.escape(date, quote=True)

        entries_xml = ""
        for entry in ledger_entries:
            safe_ledger = html.escape(entry.get("ledger_name", ""), quote=True)
            safe_amount = html.escape(entry.get("amount", "0"), quote=True)
            entries_xml += (
                "<ALLLEDGERENTRIES.LIST>"
                f"<LEDGERNAME>{safe_ledger}</LEDGERNAME>"
                f"<AMOUNT>{safe_amount}</AMOUNT>"
                "</ALLLEDGERENTRIES.LIST>"
            )

        narration_xml = ""
        if narration:
            escaped = html.escape(narration, quote=True)
            narration_xml = f"<NARRATION>{escaped}</NARRATION>"

        vch_num_xml = ""
        if voucher_number:
            escaped = html.escape(voucher_number, quote=True)
            vch_num_xml = f"<VOUCHERNUMBER>{escaped}</VOUCHERNUMBER>"

        party_xml = ""
        if party_ledger:
            escaped = html.escape(party_ledger, quote=True)
            party_xml = f"<PARTYLEDGERNAME>{escaped}</PARTYLEDGERNAME>"

        return (
            f'<VOUCHER VCHTYPE="{safe_type}" ACTION="{safe_action}">'
            f"<DATE>{safe_date}</DATE>"
            f"{vch_num_xml}"
            f"{party_xml}"
            f"{narration_xml}"
            f"{entries_xml}"
            f"</VOUCHER>"
        )

    @staticmethod
    def build_cancel_voucher_xml(
        guid: str,
        voucher_type: str = "Sales",
    ) -> str:
        """Build a ``<VOUCHER>`` XML fragment to cancel a voucher by GUID.

        Args:
            guid: The GUID of the voucher to cancel.
            voucher_type: Voucher type name.

        Returns:
            XML string fragment suitable for ``import_vouchers()``.
        """
        safe_guid = html.escape(guid, quote=True)
        safe_type = html.escape(voucher_type, quote=True)
        return (
            f'<VOUCHER VCHTYPE="{safe_type}" ACTION="Alter">'
            f"<GUID>{safe_guid}</GUID>"
            f"<ISCANCELLED>Yes</ISCANCELLED>"
            f"</VOUCHER>"
        )

    @staticmethod
    def build_ledger_json(
        name: str,
        parent_group: str = "Sundry Debtors",
        opening_balance: str = "0",
        action: str = "Create",
    ) -> dict[str, Any]:
        """Build a ledger JSON object for import via ``import_masters_json()``.

        Args:
            name: Ledger name.
            parent_group: Parent group name.
            opening_balance: Opening balance string.
            action: Import action — ``"Create"``, ``"Alter"``, ``"Delete"``.

        Returns:
            A ``tallymessage`` dict suitable for ``import_masters_json()``.
        """
        return {
            "ledger": {
                "name": name,
                "action": action,
                "parent": parent_group,
                "openingbalance": opening_balance,
            }
        }

    @staticmethod
    def build_voucher_json(
        voucher_type: str,
        date: str,
        ledger_entries: list[dict[str, str]],
        narration: str | None = None,
        voucher_number: str | None = None,
        party_ledger: str | None = None,
        action: str = "Create",
    ) -> dict[str, Any]:
        """Build a voucher JSON object for import via ``import_vouchers_json()``.

        Args:
            voucher_type: Voucher type name.
            date: Date in YYYYMMDD format.
            ledger_entries: List of dicts with ``"ledger_name"`` and ``"amount"``.
            narration: Optional narration.
            voucher_number: Optional voucher number.
            party_ledger: Optional party ledger name.
            action: Import action.

        Returns:
            A ``tallymessage`` dict suitable for ``import_vouchers_json()``.
        """
        entries = []
        for entry in ledger_entries:
            entries.append(
                {
                    "ledgername": entry.get("ledger_name", ""),
                    "amount": entry.get("amount", "0"),
                }
            )

        voucher: dict[str, Any] = {
            "vouchertype": voucher_type,
            "action": action,
            "date": date,
            "allledgerentrieslist": entries,
        }
        if narration:
            voucher["narration"] = narration
        if voucher_number:
            voucher["vouchernumber"] = voucher_number
        if party_ledger:
            voucher["partyledgername"] = party_ledger

        return {"voucher": voucher}

    @staticmethod
    def build_cancel_voucher_json(
        guid: str,
        voucher_type: str = "Sales",
    ) -> dict[str, Any]:
        """Build a voucher JSON to cancel a voucher by GUID.

        Args:
            guid: The GUID of the voucher to cancel.
            voucher_type: Voucher type name.

        Returns:
            A ``tallymessage`` dict suitable for ``import_vouchers_json()``.
        """
        return {
            "voucher": {
                "vouchertype": voucher_type,
                "action": "Alter",
                "guid": guid,
                "iscancelled": "Yes",
            }
        }

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "TallyConnection":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

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
        safe_collection = html.escape(collection_name, quote=True)
        safe_type = html.escape(tally_type, quote=True)
        fetch_tags = html.escape(",".join(fields), quote=True)
        static_vars = "<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
        if company:
            static_vars += (
                f"<SVCURRENTCOMPANY>"
                f"{html.escape(company, quote=True)}"
                f"</SVCURRENTCOMPANY>"
            )

        filter_section = ""
        if filter_expr:
            filter_section = "<FILTER>AltFilter</FILTER>"
            escaped_filter = html.escape(filter_expr, quote=True)
            filter_section += (
                f'<SYSTEM TYPE="Formulae" NAME="AltFilter">{escaped_filter}</SYSTEM>'
            )

        return (
            "<ENVELOPE>"
            "<HEADER><VERSION>1</VERSION>"
            "<TALLYREQUEST>Export Data</TALLYREQUEST>"
            f"<TYPE>Collection</TYPE><ID>{safe_collection}</ID></HEADER>"
            "<BODY><DESC><STATICVARIABLES>"
            f"{static_vars}"
            "</STATICVARIABLES>"
            "<TDL><TDLMESSAGE>"
            f'<COLLECTION NAME="{safe_collection}" ISMODIFY="No">'
            f"<TYPE>{safe_type}</TYPE>"
            f"<FETCH>{fetch_tags}</FETCH>"
            f"{filter_section}"
            "</COLLECTION>"
            "</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"
        )

    @staticmethod
    def _build_object_xml(
        tally_type: str,
        name: str | None = None,
        guid: str | None = None,
        company: str | None = None,
    ) -> str:
        """Build XML for a single-object export (TYPE=Object)."""
        safe_type = html.escape(tally_type, quote=True)
        static_vars = "<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
        if company:
            static_vars += (
                f"<SVCURRENTCOMPANY>"
                f"{html.escape(company, quote=True)}"
                f"</SVCURRENTCOMPANY>"
            )

        object_id = ""
        if name:
            object_id = html.escape(name, quote=True)
        elif guid:
            object_id = html.escape(guid, quote=True)

        return (
            "<ENVELOPE>"
            "<HEADER><VERSION>1</VERSION>"
            "<TALLYREQUEST>Export Data</TALLYREQUEST>"
            f"<TYPE>Object</TYPE><ID>{safe_type}</ID></HEADER>"
            "<BODY><DESC><STATICVARIABLES>"
            f"{static_vars}"
            f"<SVOBJECTNAME>{object_id}</SVOBJECTNAME>"
            "</STATICVARIABLES></DESC></BODY></ENVELOPE>"
        )

    @staticmethod
    def _build_report_xml(
        report_name: str,
        from_date: str | None = None,
        to_date: str | None = None,
        company: str | None = None,
    ) -> str:
        """Build XML for a computed report export (TYPE=Data)."""
        safe_report = html.escape(report_name, quote=True)
        static_vars = "<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
        if company:
            static_vars += (
                f"<SVCURRENTCOMPANY>"
                f"{html.escape(company, quote=True)}"
                f"</SVCURRENTCOMPANY>"
            )
        if from_date:
            static_vars += (
                f"<SVFROMDATE>{html.escape(from_date, quote=True)}</SVFROMDATE>"
            )
        if to_date:
            static_vars += f"<SVTODATE>{html.escape(to_date, quote=True)}</SVTODATE>"

        return (
            "<ENVELOPE>"
            "<HEADER><VERSION>1</VERSION>"
            "<TALLYREQUEST>Export Data</TALLYREQUEST>"
            f"<TYPE>Data</TYPE><ID>{safe_report}</ID></HEADER>"
            "<BODY><DESC><STATICVARIABLES>"
            f"{static_vars}"
            "</STATICVARIABLES></DESC></BODY></ENVELOPE>"
        )

    @staticmethod
    def _build_collection_json(
        collection_name: str,
        tally_type: str,
        fields: list[str],
        filter_expr: str | None = None,
        company: str | None = None,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Build HTTP headers and JSON body for a TallyPrime 7.0+ Collection export.

        Returns (headers_dict, body_dict) suitable for post_json().
        """
        headers: dict[str, str] = {
            "tallyrequest": "Export",
            "type": "Collection",
            "id": collection_name,
        }

        static_variables: dict[str, str] = {
            "svexportformat": "JSONEx",
        }
        if company:
            static_variables["svcurrentcompany"] = company

        tdl_message: dict[str, Any] = {
            "collection": {
                "name": collection_name,
                "ismodify": "No",
                "type": tally_type,
                "fetch": ",".join(fields),
            }
        }
        if filter_expr:
            tdl_message["collection"]["filter"] = "AltFilter"
            tdl_message["system"] = {
                "type": "Formulae",
                "name": "AltFilter",
                "text": filter_expr,
            }

        body: dict[str, Any] = {
            "static_variables": static_variables,
            "tdlmessage": [tdl_message],
        }

        return headers, body

    @staticmethod
    def _build_object_json(
        tally_type: str,
        name: str | None = None,
        guid: str | None = None,
        company: str | None = None,
        supports_base64: bool = False,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Build HTTP headers and JSON body for a TallyPrime 7.0+ Object export.

        Returns (headers_dict, body_dict) suitable for post_json().
        """
        headers: dict[str, str] = {
            "tallyrequest": "Export",
            "type": "Object",
            "subtype": tally_type,
        }

        if guid:
            headers["id"] = guid
        elif name:
            headers["id"] = name
            if supports_base64 and name and not name.isascii():
                headers["id-encoded"] = TallyConnection.encode_name_base64(name)

        static_variables: dict[str, str] = {
            "svexportformat": "JSONEx",
        }
        if company:
            static_variables["svcurrentcompany"] = company
            if supports_base64 and not company.isascii():
                headers["id-encoded"] = TallyConnection.encode_name_base64(company)

        body: dict[str, Any] = {
            "static_variables": static_variables,
        }

        return headers, body

    @staticmethod
    def _build_report_json(
        report_name: str,
        from_date: str | None = None,
        to_date: str | None = None,
        company: str | None = None,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """Build HTTP headers and JSON body for a TallyPrime 7.0+ Data (report) export.

        Returns (headers_dict, body_dict) suitable for post_json().
        """
        headers: dict[str, str] = {
            "tallyrequest": "Export",
            "type": "Data",
            "id": report_name,
        }

        static_variables: dict[str, str] = {
            "svexportformat": "JSONEx",
            "svexportinplainformat": "Yes",
        }
        if company:
            static_variables["svcurrentcompany"] = company
        if from_date:
            static_variables["svfromdate"] = from_date
        if to_date:
            static_variables["svtodate"] = to_date

        body: dict[str, Any] = {
            "static_variables": static_variables,
        }

        return headers, body
