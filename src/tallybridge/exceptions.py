"""Custom exceptions — see SPECS.md §1."""


class TallyConnectionError(Exception):
    """TallyPrime is not running or not reachable on the configured host:port.

    Always include a human-readable fix instruction in the message, e.g.:
    "Could not connect to Tally on localhost:9000.
     Is TallyPrime open? Enable: F1 > Settings > Connectivity >
     TallyPrime acts as = Server, Port = 9000"
    """


class TallyDataError(Exception):
    """Tally returned a LINEERROR or structurally invalid XML response.

    Store the raw response in self.raw_response for debugging.
    Extract and store the error text in self.error_text.
    """

    def __init__(
        self,
        message: str,
        raw_response: str | None = None,
        error_text: str | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        self.error_text = error_text


class TallySyncError(Exception):
    """An unrecoverable sync failure (data corruption, programmer error).

    NOT raised for temporary Tally-offline situations — those return
    SyncResult(success=False). Only raise this for situations where
    continuing would corrupt the cache.
    """


class TallyBridgeCacheError(Exception):
    """DuckDB is inaccessible, corrupted, or an unrecoverable SQL error occurred."""
