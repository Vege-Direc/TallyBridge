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
    from tallybridge.models.report import TallyReport
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
                    f" Read timeout is {self._config.tally_port}. "
                    f"Try reducing VOUCHER_BATCH_SIZE if syncing large datasets."
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
                timeout_hint = (
                    " Read timeout. Try reducing VOUCHER_BATCH_SIZE."
                )
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
