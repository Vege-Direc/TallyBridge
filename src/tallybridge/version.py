"""Tally product version detection and compatibility.

TallyPrime Release History (India market):
  - Tally.ERP 9: Pre-2020 (deprecated, no longer receiving updates)
  - TallyPrime 1.x: 2020-2021 (initial release)
  - TallyPrime 2.0: 2021 (E-Way Bill auto-generation)
  - TallyPrime 2.1: 2022 (UI refinements)
  - TallyPrime 3.0: 2023 (Reporting, multi-company)
  - TallyPrime 4.0: 2024 (Connected GST, GSTR-1 direct filing)
  - TallyPrime 5.0: 2024 (GSTR-3B, TDS automation)
  - TallyPrime 6.0: 2024 (Connected Banking)
  - TallyPrime 6.1: 2024 (Invoice Management System, Edit Log)
  - TallyPrime 6.2: 2025 (Arabic invoicing, UAE VAT)
  - TallyPrime 7.0: Dec 2025 (TallyDrive, SmartFind, cloud backup)

Market context (Gartner India 2024): 75%+ of Indian SMEs rely on Tally for
core accounting. Most users with active TSS are on TallyPrime 4.0+ since
Connected GST is essential for compliance. Tally.ERP 9 is still in use by
businesses without active TSS but is no longer receiving feature updates.

Version detection uses $$SysInfo:Version via a TDL Collection query.
"""

import re
from enum import IntEnum
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from tallybridge.connection import TallyConnection


class TallyProduct(IntEnum):
    ERP9 = 0
    PRIME_1 = 1
    PRIME_2 = 2
    PRIME_3 = 3
    PRIME_4 = 4
    PRIME_5 = 5
    PRIME_6 = 6
    PRIME_7 = 7

    @property
    def is_prime(self) -> bool:
        return self >= TallyProduct.PRIME_1

    @property
    def is_erp9(self) -> bool:
        return self == TallyProduct.ERP9

    @property
    def supports_connected_gst(self) -> bool:
        return self >= TallyProduct.PRIME_4

    @property
    def supports_connected_banking(self) -> bool:
        return self >= TallyProduct.PRIME_6

    @property
    def supports_allledger_entries(self) -> bool:
        return self >= TallyProduct.PRIME_1

    @property
    def display_name(self) -> str:
        names = {
            TallyProduct.ERP9: "Tally.ERP 9",
            TallyProduct.PRIME_1: "TallyPrime 1.x",
            TallyProduct.PRIME_2: "TallyPrime 2.x",
            TallyProduct.PRIME_3: "TallyPrime 3.x",
            TallyProduct.PRIME_4: "TallyPrime 4.x",
            TallyProduct.PRIME_5: "TallyPrime 5.x",
            TallyProduct.PRIME_6: "TallyPrime 6.x",
            TallyProduct.PRIME_7: "TallyPrime 7.x",
        }
        return names.get(self, f"Unknown ({self.value})")


def parse_version_string(version_str: str) -> TallyProduct:
    """Parse a Tally version string into a TallyProduct enum.

    Known version string formats from $$SysInfo:Version:
      - "Tally.ERP 9"          → ERP9
      - "TallyPrime"            → PRIME_1 (baseline)
      - "TallyPrime 2.0"       → PRIME_2
      - "TallyPrime Release 4" → PRIME_4
      - "4.0.1"                 → PRIME_4 (numeric-only)
      - "TallyPrime 7.0"       → PRIME_7
    """
    if not version_str or not version_str.strip():
        return TallyProduct.ERP9

    v = version_str.strip()

    erp9_patterns = [
        r"(?i)tally\.?\s*erp",
        r"(?i)erp\s*9",
    ]
    for pat in erp9_patterns:
        if re.search(pat, v):
            return TallyProduct.ERP9

    prime_match = re.search(r"(?i)tally\s*prime", v)
    if prime_match:
        num_match = re.search(r"(\d+)(?:\.\d+)*", v[prime_match.end() :])
        if num_match:
            major = int(num_match.group(1))
            if major >= 7:
                return TallyProduct.PRIME_7
            if major >= 6:
                return TallyProduct.PRIME_6
            if major >= 5:
                return TallyProduct.PRIME_5
            if major >= 4:
                return TallyProduct.PRIME_4
            if major >= 3:
                return TallyProduct.PRIME_3
            if major >= 2:
                return TallyProduct.PRIME_2
            return TallyProduct.PRIME_1
        release_match = re.search(r"(?i)release\s*(\d+)", v)
        if release_match:
            major = int(release_match.group(1))
            if major >= 7:
                return TallyProduct.PRIME_7
            if major >= 6:
                return TallyProduct.PRIME_6
            if major >= 5:
                return TallyProduct.PRIME_5
            if major >= 4:
                return TallyProduct.PRIME_4
            if major >= 3:
                return TallyProduct.PRIME_3
            if major >= 2:
                return TallyProduct.PRIME_2
        return TallyProduct.PRIME_1

    num_match = re.match(r"(\d+)", v)
    if num_match:
        major = int(num_match.group(1))
        if major >= 7:
            return TallyProduct.PRIME_7
        if major >= 6:
            return TallyProduct.PRIME_6
        if major >= 5:
            return TallyProduct.PRIME_5
        if major >= 4:
            return TallyProduct.PRIME_4
        if major >= 3:
            return TallyProduct.PRIME_3
        if major >= 2:
            return TallyProduct.PRIME_2
        if major == 1:
            return TallyProduct.PRIME_1
        return TallyProduct.ERP9

    return TallyProduct.ERP9


_VERSION_DETECT_XML = """\
<ENVELOPE>
<HEADER><VERSION>1</VERSION>
<TALLYREQUEST>Export</TALLYREQUEST>
<TYPE>Collection</TYPE>
<ID>VersionInfo</ID></HEADER>
<BODY><DESC><STATICVARIABLES>
<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
</STATICVARIABLES>
<TDL><TDLMESSAGE>
<COLLECTION NAME="VersionInfo" ISMODIFY="No">
<TYPE>Company</TYPE>
<NATIVEMETHOD>Version</NATIVEMETHOD>
</COLLECTION>
</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"""


async def detect_tally_version(
    connection: "TallyConnection",
) -> TallyProduct:
    """Query Tally for its product version using $$SysInfo:Version.

    Falls back to TallyProduct.ERP9 if detection fails.
    Caches the result on the connection object for reuse.
    """
    if (
        hasattr(connection, "_detected_version")
        and connection._detected_version is not None
    ):
        return connection._detected_version

    try:
        response = await connection.post_xml(_VERSION_DETECT_XML)
        version_match = re.search(
            r"<VERSION>([^<]+)</VERSION>", response, re.IGNORECASE
        )
        if version_match:
            version_str = version_match.group(1).strip()
            product = parse_version_string(version_str)
            logger.info(
                "Detected Tally version: '{}' → {}",
                version_str,
                product.display_name,
            )
        else:
            name_match = re.search(r"<COMPANY[^>]*>\s*<NAME>", response)
            if name_match:
                product = TallyProduct.PRIME_1
                logger.info(
                    "Tally responded with company data but no version tag; "
                    "assuming TallyPrime 1.x+"
                )
            else:
                product = TallyProduct.ERP9
                logger.warning(
                    "Could not detect Tally version from response; "
                    "assuming Tally.ERP 9"
                )
    except Exception as exc:
        product = TallyProduct.ERP9
        logger.warning("Tally version detection failed: {}; assuming ERP 9", exc)

    connection._detected_version = product
    return product
