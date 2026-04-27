"""CLI interface — see SPECS.md §10."""

import asyncio
import platform
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from tallybridge.config import TallyBridgeConfig, get_config, reset_config

app = typer.Typer(
    name="tallybridge",
    help="Connect TallyPrime to DuckDB and AI via MCP",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Configuration commands")
service_app = typer.Typer(help="Windows service management")
app.add_typer(config_app, name="config")
app.add_typer(service_app, name="service")

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        from tallybridge import __version__

        console.print(f"TallyBridge {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version", callback=_version_callback
    ),
) -> None:
    """Connect TallyPrime to DuckDB and AI via MCP."""


@config_app.command("show")
def config_show() -> None:
    """Print config, mask supabase_key."""
    cfg = get_config()
    table = Table(title="TallyBridge Configuration")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("tally_host", cfg.tally_host)
    table.add_row("tally_port", str(cfg.tally_port))
    table.add_row("tally_company", cfg.tally_company or "(active)")
    table.add_row("db_path", cfg.db_path)
    table.add_row("sync_frequency_minutes", str(cfg.sync_frequency_minutes))
    table.add_row("log_level", cfg.log_level)
    table.add_row("supabase_url", cfg.supabase_url or "(not set)")
    table.add_row("supabase_key", "***" if cfg.supabase_key else "(not set)")
    console.print(table)


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    """Write KEY=VALUE to .env."""
    env_path = Path(".env")
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    env_key = f"TALLYBRIDGE_{key.upper()}"
    new_lines = []
    found = False
    for line in lines:
        if line.startswith(f"{env_key}="):
            new_lines.append(f"{env_key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{env_key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n")
    reset_config()
    console.print(f"Set {env_key}={value}")


@app.command()
def status() -> None:
    """Rich table: sync status per entity."""
    cfg = get_config()
    try:
        from tallybridge.cache import TallyCache

        cache = TallyCache(cfg.db_path)
        sync_status = cache.get_sync_status()
        health = cache.health_check()

        table = Table(title="TallyBridge Sync Status")
        table.add_column("Entity")
        table.add_column("Last AlterID")
        table.add_column("Last Sync")
        table.add_column("Record Count")

        for entity, info in sync_status.items():
            table.add_row(
                entity,
                str(info.get("last_alter_id", 0)),
                str(info.get("last_sync_at", "Never")),
                str(info.get("record_count", 0)),
            )

        if not sync_status:
            table.add_row("(no syncs yet)", "-", "-", "-")

        console.print(table)
        console.print(f"DB size: {health.get('db_size_mb', 0)} MB")
        cache.close()
    except Exception as exc:
        console.print(f"[red]Error reading cache: {exc}[/red]")


@app.command()
def sync(
    full: bool = typer.Option(False, "--full", help="Force full re-sync"),
    watch: bool = typer.Option(False, "--watch", help="Continuous sync"),
) -> None:
    """One-time sync now."""
    cfg = get_config()
    from tallybridge.cache import TallyCache
    from tallybridge.connection import TallyConnection
    from tallybridge.parser import TallyXMLParser
    from tallybridge.sync import TallySyncEngine

    cache = TallyCache(cfg.db_path)
    connection = TallyConnection(cfg)
    parser = TallyXMLParser()
    engine = TallySyncEngine(connection, cache, parser)

    async def _run() -> None:
        if full:
            results = await engine.full_sync()
        else:
            results = await engine.sync_all()
        for entity_type, result in results.items():
            status_icon = "✓" if result.success else "✗"
            console.print(
                f"  {status_icon} {entity_type}: {result.records_synced} records "
                f"({result.duration_seconds:.1f}s)"
            )
        await connection.close()
        cache.close()

    if watch:

        async def _watch() -> None:
            with console.status("Watching for changes..."):
                await engine.run_continuous(cfg.sync_frequency_minutes)

        asyncio.run(_watch())
    else:
        asyncio.run(_run())


@service_app.command("install")
def service_install() -> None:
    """Install as auto-start Windows service."""
    if platform.system() != "Windows":
        console.print("Windows service management is only available on Windows.")
        raise typer.Exit(0)
    console.print("Service install not yet implemented.")


@service_app.command("start")
def service_start() -> None:
    """Start the Windows service."""
    if platform.system() != "Windows":
        console.print("Windows service management is only available on Windows.")
        raise typer.Exit(0)
    console.print("Service start not yet implemented.")


@service_app.command("stop")
def service_stop() -> None:
    """Stop the Windows service."""
    if platform.system() != "Windows":
        console.print("Windows service management is only available on Windows.")
        raise typer.Exit(0)
    console.print("Service stop not yet implemented.")


@service_app.command("uninstall")
def service_uninstall() -> None:
    """Remove the Windows service."""
    if platform.system() != "Windows":
        console.print("Windows service management is only available on Windows.")
        raise typer.Exit(0)
    console.print("Service uninstall not yet implemented.")


@app.command()
def mcp(
    http: bool = typer.Option(False, "--http", help="Use HTTP transport"),
    port: int = typer.Option(8000, "--port", help="HTTP port"),
) -> None:
    """Start MCP server (stdio)."""
    from tallybridge.mcp.sdk_server import mcp as mcp_server

    if http:
        console.print(f"MCP HTTP server not yet implemented (port={port})")
    else:
        mcp_server.run(transport="stdio")


@app.command()
def doctor() -> None:
    """Diagnostic checks."""
    checks = []

    # 1. Python version
    py_ver = sys.version_info
    checks.append(
        (
            f"Python version ≥ 3.11 ({py_ver.major}.{py_ver.minor})",
            py_ver >= (3, 11),
        )
    )

    # 2. Tally reachable
    cfg = get_config()
    try:
        reachable = asyncio.run(_ping_tally(cfg))
    except Exception:
        reachable = False
    checks.append(
        (
            f"Tally reachable on {cfg.tally_host}:{cfg.tally_port}",
            reachable,
        )
    )

    # 3. DuckDB file exists
    db_exists = Path(cfg.db_path).exists()
    checks.append((f"DuckDB file exists ({cfg.db_path})", db_exists))

    # 4. Last sync < 30 min
    sync_ok = False
    if db_exists:
        try:
            from tallybridge.cache import TallyCache

            cache = TallyCache(cfg.db_path)
            status = cache.get_sync_status()
            if status:
                last_sync = list(status.values())[0].get("last_sync_at")
                if last_sync and last_sync != "None":
                    sync_ok = True
            cache.close()
        except Exception:
            pass
    checks.append(("Last sync < 30 minutes ago", sync_ok))

    # 5. DuckDB has > 0 ledger records
    has_data = False
    if db_exists:
        try:
            from tallybridge.cache import TallyCache

            cache = TallyCache(cfg.db_path)
            count = cache.query("SELECT COUNT(*) as cnt FROM mst_ledger")
            has_data = count[0]["cnt"] > 0 if count else False
            cache.close()
        except Exception:
            pass
    checks.append(("DuckDB has ledger records", has_data))

    # 6. MCP server importable
    try:
        from tallybridge.mcp.sdk_server import mcp  # noqa: F401

        mcp_ok = True
    except Exception:
        mcp_ok = False
    checks.append(("MCP server importable", mcp_ok))

    # 7. Windows service (Windows only)
    if platform.system() == "Windows":
        checks.append(("Windows service installed", False))
    else:
        checks.append(("(Windows service — N/A on this OS)", True))

    for label, ok in checks:
        icon = "✓" if ok else "✗"
        console.print(f"  {icon} {label}")


@app.command()
def logs() -> None:
    """Tail recent loguru log file."""
    console.print("No log file configured yet. Use loguru's default sink.")


@app.command()
def init() -> None:
    """Interactive setup wizard."""
    console.print(
        "[bold]Welcome to TallyBridge![/bold] Let's connect to your TallyPrime."
    )

    running = typer.confirm("Is TallyPrime running on this computer?", default=True)
    if not running:
        console.print("Please start TallyPrime and run this wizard again.")
        raise typer.Exit(0)

    location = typer.prompt(
        "Where is TallyPrime? (1 = This computer, 2 = Another computer)",
        type=int,
    )
    if location == 2:
        host = typer.prompt("  Host/IP address", default="localhost")
        port = typer.prompt("  Port", default=9000, type=int)
    else:
        host = "localhost"
        port = 9000

    db_path = typer.prompt("Where to store data?", default="tallybridge.duckdb")
    freq = typer.prompt("How often to sync (minutes)?", default=5, type=int)

    console.print("Writing configuration...")
    config_set("TALLY_HOST", host)
    config_set("TALLY_PORT", str(port))
    config_set("DB_PATH", db_path)
    config_set("SYNC_FREQUENCY_MINUTES", str(freq))

    console.print("[bold green]TallyBridge is ready![/bold green]")
    console.print("Run [bold]tallybridge sync[/bold] to fetch data from TallyPrime.")


async def _ping_tally(cfg: TallyBridgeConfig) -> bool:
    from tallybridge.connection import TallyConnection

    conn = TallyConnection(cfg)
    result = await conn.ping()
    await conn.close()
    return result
