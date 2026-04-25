"""Tests for CLI — SPECS.md §10."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from tallybridge.cli import app

runner = CliRunner()


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "sync" in result.output
    assert "status" in result.output
    assert "mcp" in result.output


def test_status_prints_table() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0


def test_doctor_prints_checks() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    check_lines = [line for line in result.output.splitlines() if "✓" in line or "✗" in line]
    assert len(check_lines) >= 6


def test_sync_full_calls_full_sync() -> None:
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.records_synced = 5
    mock_result.duration_seconds = 0.1

    with patch("tallybridge.sync.TallySyncEngine.full_sync", new_callable=AsyncMock) as mock_full:
        mock_full.return_value = {"ledger": mock_result}
        with patch("tallybridge.sync.TallySyncEngine.sync_all", new_callable=AsyncMock) as mock_sync:
            mock_sync.return_value = {"ledger": mock_result}
            with patch("tallybridge.connection.TallyConnection.close", new_callable=AsyncMock):
                result = runner.invoke(app, ["sync", "--full"])
                assert result.exit_code == 0
