"""Optional offline presentation of public analysis results."""

from __future__ import annotations

from check_yourself.api import AnalysisResult
from check_yourself.models import AnalysisReport, AnalysisRunSettings


class ReportError(Exception):
    """An optional report dependency is unavailable."""


def render_html(result: AnalysisResult) -> str:
    """Return standalone HTML. Install check-yourself-chess[html] to use it."""
    try:
        from check_yourself.reports.html import render_html_report
    except ModuleNotFoundError as exc:
        if exc.name not in {"jinja2", "plotly"}:
            raise
        raise ReportError("HTML output requires check-yourself-chess[html]") from exc

    label = result.player or f"{result.games[0].metadata.user_color.capitalize()} side"
    engine = result.provenance
    report = AnalysisReport(
        schema_version=result.schema_version,
        settings=AnalysisRunSettings(
            username=label, platform="local PGN", games_requested=len(result.games),
            games_found=len(result.games), stockfish_path="", depth=engine.depth,
            multipv=1, pv_moves=engine.pv_moves, inaccuracy_threshold=50,
            mistake_threshold=100, blunder_threshold=200,
            max_critical_positions=engine.max_critical_positions, analyzed_at=None,
            stockfish_version=engine.stockfish_version,
        ),
        overall=result.overall,
        games=result.games,
        behavior=result.behavior,
        tactics=result.tactics,
    )
    return render_html_report(report, label, include_branding=False)
