"""Tests for CLI — SPECS.md §10."""

from unittest.mock import AsyncMock, MagicMock, patch

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
    check_lines = [
        line for line in result.output.splitlines() if "✓" in line or "✗" in line
    ]
    assert len(check_lines) >= 6


def test_sync_full_calls_full_sync() -> None:
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.records_synced = 5
    mock_result.duration_seconds = 0.1

    with patch(
        "tallybridge.sync.TallySyncEngine.full_sync", new_callable=AsyncMock
    ) as mock_full:
        mock_full.return_value = {"ledger": mock_result}
        with patch(
            "tallybridge.sync.TallySyncEngine.sync_all", new_callable=AsyncMock
        ) as mock_sync:
            mock_sync.return_value = {"ledger": mock_result}
            with patch(
                "tallybridge.connection.TallyConnection.close", new_callable=AsyncMock
            ):
                result = runner.invoke(app, ["sync", "--full"])
                assert result.exit_code == 0


def test_sync_without_full_calls_sync_all() -> None:
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.records_synced = 3
    mock_result.duration_seconds = 0.2

    with patch(
        "tallybridge.sync.TallySyncEngine.full_sync", new_callable=AsyncMock
    ) as mock_full:
        with patch(
            "tallybridge.sync.TallySyncEngine.sync_all", new_callable=AsyncMock
        ) as mock_sync:
            mock_sync.return_value = {"ledger": mock_result}
            with patch(
                "tallybridge.connection.TallyConnection.close", new_callable=AsyncMock
            ):
                result = runner.invoke(app, ["sync"])
                assert result.exit_code == 0
                mock_sync.assert_called_once()
                mock_full.assert_not_called()


def test_config_show() -> None:
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "tally_host" in result.output


def test_config_set(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["config", "set", "TALLY_HOST", "myhost"])
    assert result.exit_code == 0
    assert "TALLYBRIDGE_TALLY_HOST=myhost" in result.output


def test_config_set_new_key(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("TALLYBRIDGE_EXISTING_KEY=value\n")
    result = runner.invoke(app, ["config", "set", "NEW_KEY", "newval"])
    assert result.exit_code == 0
    content = env_file.read_text()
    assert "TALLYBRIDGE_NEW_KEY=newval" in content
    assert "TALLYBRIDGE_EXISTING_KEY=value" in content


def test_mcp_command_stdio() -> None:
    with patch("tallybridge.mcp.sdk_server.mcp") as mock_mcp:
        runner.invoke(app, ["mcp"])
        mock_mcp.run.assert_called_once_with(transport="stdio")


def test_mcp_command_http() -> None:
    result = runner.invoke(app, ["mcp", "--http"])
    assert result.exit_code == 0
    assert "HTTP" in result.output


def test_service_install_non_windows() -> None:
    with patch("tallybridge.cli.platform.system", return_value="Linux"):
        result = runner.invoke(app, ["service", "install"])
        assert result.exit_code == 0


def test_service_start_non_windows() -> None:
    with patch("tallybridge.cli.platform.system", return_value="Linux"):
        result = runner.invoke(app, ["service", "start"])
        assert result.exit_code == 0


def test_service_stop_non_windows() -> None:
    with patch("tallybridge.cli.platform.system", return_value="Linux"):
        result = runner.invoke(app, ["service", "stop"])
        assert result.exit_code == 0


def test_service_uninstall_non_windows() -> None:
    with patch("tallybridge.cli.platform.system", return_value="Linux"):
        result = runner.invoke(app, ["service", "uninstall"])
        assert result.exit_code == 0


def test_service_install_windows() -> None:
    with patch("tallybridge.cli.platform.system", return_value="Windows"):
        result = runner.invoke(app, ["service", "install"])
        assert "not yet implemented" in result.output.lower()


def test_service_start_windows() -> None:
    with patch("tallybridge.cli.platform.system", return_value="Windows"):
        result = runner.invoke(app, ["service", "start"])
        assert "not yet implemented" in result.output.lower()


def test_service_stop_windows() -> None:
    with patch("tallybridge.cli.platform.system", return_value="Windows"):
        result = runner.invoke(app, ["service", "stop"])
        assert "not yet implemented" in result.output.lower()


def test_service_uninstall_windows() -> None:
    with patch("tallybridge.cli.platform.system", return_value="Windows"):
        result = runner.invoke(app, ["service", "uninstall"])
        assert "not yet implemented" in result.output.lower()


def test_logs_command() -> None:
    result = runner.invoke(app, ["logs"])
    assert result.exit_code == 0
    assert "log" in result.output.lower()


def test_init_command_local_setup() -> None:
    with patch("tallybridge.cli.config_set"):
        with patch(
            "tallybridge.cli._detect_tally_port",
            return_value=9000,
        ):
            with patch(
                "tallybridge.cli._list_companies",
                return_value=["Test Company"],
            ):
                result = runner.invoke(
                    app, ["init"],
                    input="1\n\n\ntest.duckdb\n5\n",
                )
                assert result.exit_code == 0
                assert "tallybridge" in result.output.lower()


def test_init_command_remote_setup() -> None:
    with patch("tallybridge.cli.config_set"):
        with patch(
            "tallybridge.cli._detect_tally_port",
            return_value=9001,
        ):
            with patch(
                "tallybridge.cli._list_companies",
                return_value=[],
            ):
                result = runner.invoke(
                    app, ["init"],
                    input="2\n192.168.1.100\nremote.duckdb\n10\n",
                )
                assert result.exit_code == 0


def test_status_command_with_error() -> None:
    with patch("tallybridge.cache.TallyCache", side_effect=Exception("db error")):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "error" in result.output.lower()


def test_doctor_non_windows() -> None:
    with patch("tallybridge.cli.platform.system", return_value="Linux"):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "N/A" in result.output


def test_doctor_tss_expired_shows_renewal_prompt() -> None:
    from tallybridge.version import TallyProduct

    mock_product = TallyProduct.PRIME_4
    with patch(
        "tallybridge.cli._ping_tally",
        new_callable=AsyncMock,
        return_value=True,
    ):
        with patch(
            "tallybridge.connection.TallyConnection.detect_version",
            new_callable=AsyncMock,
            return_value=mock_product,
        ):
            with patch(
                "tallybridge.connection.TallyConnection.close",
                new_callable=AsyncMock,
            ):
                result = runner.invoke(app, ["doctor"])
                assert result.exit_code == 0
                assert "tallysolutions.com" in result.output


def test_doctor_tss_active_no_renewal_prompt() -> None:
    from tallybridge.version import TallyProduct

    mock_product = TallyProduct.PRIME_7
    with patch(
        "tallybridge.cli._ping_tally",
        new_callable=AsyncMock,
        return_value=True,
    ):
        with patch(
            "tallybridge.connection.TallyConnection.detect_version",
            new_callable=AsyncMock,
            return_value=mock_product,
        ):
            with patch(
                "tallybridge.connection.TallyConnection.close",
                new_callable=AsyncMock,
            ):
                result = runner.invoke(app, ["doctor"])
                assert result.exit_code == 0
                assert "TSS subscription active" in result.output
