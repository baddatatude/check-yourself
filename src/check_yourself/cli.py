"""Check Yourself command-line interface."""

from __future__ import annotations

import logging
import sys
from getpass import getpass
from pathlib import Path

import typer
from pydantic import SecretStr
from rich.console import Console
from rich.table import Table

from check_yourself import __version__
from check_yourself.config import AnalysisSettings, TimeControlFilter
from check_yourself.engine.stockfish import EngineError, probe_stockfish
from check_yourself.pipeline import AnalysisPipeline
from check_yourself.providers.base import ProviderError, normalize_platform
from check_yourself.providers.chess_com import ChessComError, probe_chess_com, validate_username
from check_yourself.providers.coaching import probe_openai_key
from check_yourself.providers.lichess import LichessError, probe_lichess, validate_lichess_username

app = typer.Typer(
    name="check-yourself",
    help=(
        "Download Chess.com or Lichess games, analyze them with Stockfish, "
        "and generate visual reports.\n\n"
        "Check yourself before your rating wrecks itself."
    ),
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"check-yourself {__version__}")
        raise typer.Exit()


def _resolve_api_key_for_coach(settings: AnalysisSettings, explicit: str | None) -> str | None:
    """Resolve OpenAI key safely: CLI override → env/.env → hidden prompt."""
    if explicit is not None and explicit.strip():
        settings.openai_api_key = SecretStr(explicit.strip())
        return settings.resolve_openai_api_key()

    key = settings.resolve_openai_api_key()
    if key:
        return key

    console.print(
        "[yellow]OpenAI API key not found in environment.[/yellow] "
        "Enter it now (input hidden). Prefer setting OPENAI_API_KEY or "
        "CHECK_YOURSELF_OPENAI_API_KEY in a local .env file."
    )
    try:
        entered = getpass("OpenAI API key: ").strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise typer.Exit(code=2) from exc
    if not entered:
        return None
    settings.openai_api_key = SecretStr(entered)
    return entered


def _validate_username_for_platform(platform: str, username: str) -> None:
    if platform == "lichess":
        validate_lichess_username(username)
    else:
        validate_username(username)


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Check Yourself CLI."""


@app.command("analyze")
def analyze_cmd(
    username: str = typer.Argument(..., help="Chess.com or Lichess username"),
    platform: str = typer.Option(
        "chess.com",
        "--platform",
        "-p",
        help="Game site: chess.com or lichess",
    ),
    games: int = typer.Option(10, "--games", "-n", min=1, max=500, help="Number of recent games"),
    time_control: TimeControlFilter | None = typer.Option(
        None,
        "--time-control",
        "-t",
        help="Filter: bullet, blitz, rapid, daily, or classical",
    ),
    stockfish_path: Path | None = typer.Option(
        None,
        "--stockfish-path",
        help="Path to Stockfish binary",
    ),
    depth: int = typer.Option(12, "--depth", "-d", min=1, max=40, help="Stockfish depth"),
    workers: int = typer.Option(
        1,
        "--workers",
        "-w",
        min=1,
        max=16,
        help="Parallel Stockfish processes (falls back to 1 on failure)",
    ),
    coach: bool = typer.Option(
        False,
        "--coach/--no-coach",
        help="Add OpenAI coaching grounded on Stockfish critical positions",
    ),
    openai_model: str = typer.Option(
        "gpt-4.1-mini",
        "--openai-model",
        help="OpenAI model used when --coach is set",
    ),
    openai_api_key: str | None = typer.Option(
        None,
        "--openai-api-key",
        help="OpenAI API key (prefer OPENAI_API_KEY env / .env; never stored in reports)",
        hide_input=True,
    ),
    output: Path = typer.Option(
        Path("reports"),
        "--output",
        "-o",
        help="Output directory for reports",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging"),
) -> None:
    """Analyze a player's recent games with Stockfish."""
    _configure_logging(verbose)
    settings = AnalysisSettings()
    if stockfish_path is not None:
        settings.stockfish_path = str(stockfish_path)
    settings.depth = depth
    settings.workers = workers
    settings.openai_model = openai_model
    settings.default_output_dir = output

    try:
        platform_name = normalize_platform(platform)
    except ProviderError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        logging.error("%s", exc)
        raise typer.Exit(code=2) from exc

    try:
        _validate_username_for_platform(platform_name, username)
    except (ChessComError, LichessError) as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    if not settings.resolve_stockfish_path():
        err_console.print(
            "[red]Error:[/red] Stockfish not found. Install Stockfish or pass --stockfish-path."
        )
        raise typer.Exit(code=3)

    if coach:
        key = _resolve_api_key_for_coach(settings, openai_api_key)
        if not key:
            err_console.print(
                "[red]Error:[/red] --coach requires an OpenAI API key "
                "(OPENAI_API_KEY, CHECK_YOURSELF_OPENAI_API_KEY, or prompt)."
            )
            raise typer.Exit(code=2)

    worker_note = f", {workers} workers" if workers > 1 else ""
    coach_note = f", coach={openai_model}" if coach else ""
    console.print(
        f"[bold]Check Yourself[/bold] — analyzing [cyan]{username}[/cyan] "
        f"on [cyan]{platform_name}[/cyan] "
        f"({games} games, depth {depth}{worker_note}{coach_note})"
    )

    try:
        pipeline = AnalysisPipeline(settings=settings)
        report, run_dir = pipeline.run(
            username,
            games=games,
            platform=platform_name,
            time_control=time_control,
            output_dir=output,
            coach=coach,
        )
    except ProviderError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        logging.error("%s", exc)
        raise typer.Exit(code=2) from exc
    except ChessComError as exc:
        err_console.print(f"[red]Chess.com error:[/red] {exc}")
        raise typer.Exit(code=4) from exc
    except LichessError as exc:
        err_console.print(f"[red]Lichess error:[/red] {exc}")
        raise typer.Exit(code=4) from exc
    except EngineError as exc:
        err_console.print(f"[red]Stockfish error:[/red] {exc}")
        raise typer.Exit(code=3) from exc
    except Exception as exc:
        err_console.print(f"[red]Unexpected error:[/red] {exc}")
        logging.exception("analyze failed")
        raise typer.Exit(code=1) from exc

    o = report.overall
    console.print()
    console.print(f"[green]Done.[/green] Analyzed {o.games_analyzed} game(s).")
    console.print(
        f"Record: {o.wins}-{o.losses}-{o.draws}  ·  "
        f"Win rate: {o.win_rate * 100:.1f}%  ·  "
        f"Median CPL: {o.median_centipawn_loss}  ·  "
        f"Avg ACPL: {o.average_centipawn_loss} (capped)"
    )
    console.print(
        f"Inaccuracies/game: {o.inaccuracies_per_game}  ·  "
        f"Mistakes/game: {o.mistakes_per_game}  ·  "
        f"Blunders/game: {o.blunders_per_game}"
    )
    console.print(f"Critical positions: {o.total_critical_positions}")
    if report.coaching is not None:
        console.print(
            f"[green]Coaching:[/green] {report.coaching.model} "
            f"({len(report.coaching.games)} game note(s))"
        )
    if report.warnings:
        console.print("[yellow]Warnings:[/yellow]")
        for w in report.warnings:
            console.print(f"  • {w}")
    console.print()
    console.print(f"HTML report:  {run_dir / 'report.html'}")
    console.print(f"JSON results: {run_dir / 'analysis.json'}")
    console.print(f"Games cache:  {run_dir / 'games'}")
    if coach or report.habits is not None:
        from check_yourself.coaching.profile_store import profile_path as _profile_path

        prof = _profile_path(
            settings.default_players_dir,
            username,
            report.settings.platform,
        )
        console.print(f"Player profile: {prof}")


@app.command("coach")
def coach_cmd(
    from_report: Path = typer.Option(
        ...,
        "--from-report",
        help="Path to analysis.json or a report directory (skips Stockfish)",
    ),
    use_llm: bool = typer.Option(
        True,
        "--llm/--no-llm",
        help="Call OpenAI (default) or only refresh habits + durable profile",
    ),
    openai_model: str = typer.Option(
        "gpt-4.1-mini",
        "--openai-model",
        help="OpenAI model used when --llm is set",
    ),
    openai_api_key: str | None = typer.Option(
        None,
        "--openai-api-key",
        help="OpenAI API key (prefer OPENAI_API_KEY env / .env)",
        hide_input=True,
    ),
    players_dir: Path = typer.Option(
        Path("players"),
        "--players-dir",
        help="Directory for durable per-player coaching profiles",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging"),
) -> None:
    """Re-coach from a saved report without re-running Stockfish."""
    from check_yourself.pipeline import recoach_from_report
    from check_yourself.providers.coaching import CoachingError

    _configure_logging(verbose)
    settings = AnalysisSettings()
    settings.openai_model = openai_model
    settings.default_players_dir = players_dir

    if use_llm:
        key = _resolve_api_key_for_coach(settings, openai_api_key)
        if not key:
            err_console.print(
                "[red]Error:[/red] LLM coaching requires an OpenAI API key "
                "(or pass --no-llm to refresh habits/profile only)."
            )
            raise typer.Exit(code=2)

    console.print(
        f"[bold]Check Yourself[/bold] — coaching from [cyan]{from_report}[/cyan]"
        f"{' (LLM)' if use_llm else ' (habits/profile only)'}"
    )

    try:
        report, analysis_path, profile_out = recoach_from_report(
            from_report,
            settings=settings,
            use_llm=use_llm,
        )
    except FileNotFoundError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    except CoachingError as exc:
        err_console.print(f"[red]Coaching error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        err_console.print(f"[red]Unexpected error:[/red] {exc}")
        logging.exception("coach failed")
        raise typer.Exit(code=1) from exc

    console.print()
    console.print(f"[green]Done.[/green] Updated {analysis_path}")
    if report.coaching is not None:
        console.print(
            f"Coaching model: {report.coaching.model} · "
            f"{len(report.coaching.games)} game note(s)"
        )
    if report.habits is not None:
        console.print(f"Habit findings: {len(report.habits.findings)}")
    if profile_out is not None:
        console.print(f"Player profile: {profile_out}")
    if report.warnings:
        console.print("[yellow]Warnings:[/yellow]")
        for w in report.warnings:
            console.print(f"  • {w}")
    console.print(f"HTML report:  {analysis_path.parent / 'report.html'}")


@app.command("doctor")
def doctor_cmd(
    stockfish_path: Path | None = typer.Option(
        None,
        "--stockfish-path",
        help="Optional Stockfish path to probe",
    ),
    output: Path = typer.Option(
        Path("reports"),
        "--output",
        "-o",
        help="Output directory to test for write access",
    ),
) -> None:
    """Check local environment readiness."""
    settings = AnalysisSettings()
    if stockfish_path is not None:
        settings.stockfish_path = str(stockfish_path)

    table = Table(title="Check Yourself doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")

    table.add_row(
        "Python / package",
        "[green]OK[/green]",
        f"Python {sys.version.split()[0]} · check-yourself {__version__}",
    )

    path = settings.resolve_stockfish_path()
    ok, detail = probe_stockfish(path)
    table.add_row(
        "Stockfish availability",
        "[green]OK[/green]" if ok else "[red]FAIL[/red]",
        detail,
    )
    if ok:
        table.add_row("Stockfish version", "[green]OK[/green]", detail)

    net_ok, net_detail = probe_chess_com(settings.chess_com_user_agent)
    table.add_row(
        "Chess.com API",
        "[green]OK[/green]" if net_ok else "[red]FAIL[/red]",
        net_detail,
    )

    li_ok, li_detail = probe_lichess(settings.lichess_user_agent)
    table.add_row(
        "Lichess API",
        "[green]OK[/green]" if li_ok else "[red]FAIL[/red]",
        li_detail,
    )

    key_ok, key_detail = probe_openai_key(settings.resolve_openai_api_key())
    table.add_row(
        "OpenAI API key (optional coaching)",
        "[green]OK[/green]" if key_ok else "[yellow]missing[/yellow]",
        key_detail,
    )

    try:
        output.mkdir(parents=True, exist_ok=True)
        probe = output / ".check_yourself_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        write_ok, write_detail = True, str(output.resolve())
    except OSError as exc:
        write_ok, write_detail = False, str(exc)
    table.add_row(
        "Output directory write",
        "[green]OK[/green]" if write_ok else "[red]FAIL[/red]",
        write_detail,
    )

    console.print(table)
    if not (ok and write_ok):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
