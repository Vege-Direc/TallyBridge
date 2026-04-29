"""Configuration — see SPECS.md §2."""

import httpx
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tallybridge.exceptions import TallyConnectionError


class TallyBridgeConfig(BaseSettings):
    tally_host: str = "localhost"
    tally_port: int = 9000
    tally_company: str | None = None
    tally_encoding: str = "utf-8"
    tally_export_format: str = "auto"
    strict_status: bool = False

    db_path: str = "tallybridge.duckdb"

    sync_frequency_minutes: int = 5
    voucher_batch_size: int = 5000

    log_level: str = "INFO"

    supabase_url: str | None = None
    supabase_key: str | None = None
    mcp_api_key: str | None = None
    allow_writes: bool = False

    model_config = SettingsConfigDict(
        env_prefix="TALLYBRIDGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR"}
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.upper()

    @field_validator("tally_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("tally_port must be between 1 and 65535")
        return v

    @field_validator("tally_encoding")
    @classmethod
    def validate_encoding(cls, v: str) -> str:
        allowed = {"utf-8", "utf-16"}
        if v.lower() not in allowed:
            raise ValueError(f"tally_encoding must be one of {allowed}")
        return v.lower()

    @field_validator("tally_export_format")
    @classmethod
    def validate_export_format(cls, v: str) -> str:
        allowed = {"auto", "xml", "json"}
        if v.lower() not in allowed:
            raise ValueError(f"tally_export_format must be one of {allowed}")
        return v.lower()

    @field_validator("voucher_batch_size")
    @classmethod
    def validate_voucher_batch_size(cls, v: int) -> int:
        if not 100 <= v <= 10000:
            raise ValueError("voucher_batch_size must be between 100 and 10000")
        return v

    async def validate_tally_connection(self) -> None:
        """Ping Tally and raise TallyConnectionError if unreachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    self.tally_url,
                    content=(
                        "<ENVELOPE><HEADER><VERSION>1</VERSION>"
                        "<TALLYREQUEST>Export Data</TALLYREQUEST>"
                        "<TYPE>Collection</TYPE><ID>Ping</ID></HEADER>"
                        "<BODY><DESC><STATICVARIABLES>"
                        "<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
                        "</STATICVARIABLES><TDL><TDLMESSAGE>"
                        '<COLLECTION NAME="Ping" ISMODIFY="No">'
                        "<TYPE>Company</TYPE><FETCH>NAME</FETCH>"
                        "</COLLECTION></TDLMESSAGE></TDL>"
                        "</DESC></BODY></ENVELOPE>"
                    ).encode("utf-8"),
                    headers={"Content-Type": "text/xml; charset=utf-8"},
                )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise TallyConnectionError(
                f"Could not connect to Tally on {self.tally_host}:{self.tally_port}. "
                f"Is TallyPrime open? Enable: F1 > Settings > Connectivity > "
                f"TallyPrime acts as = Server, Port = {self.tally_port}"
            ) from exc

    @property
    def tally_url(self) -> str:
        return f"http://{self.tally_host}:{self.tally_port}"


_config_instance: TallyBridgeConfig | None = None


def get_config() -> TallyBridgeConfig:
    """Return cached singleton. Safe to call from anywhere."""
    global _config_instance
    if _config_instance is None:
        _config_instance = TallyBridgeConfig()
    return _config_instance


def reset_config() -> None:
    """Reset the singleton — used in tests."""
    global _config_instance
    _config_instance = None
