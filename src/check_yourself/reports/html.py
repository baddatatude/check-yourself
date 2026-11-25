"""HTML report generation."""

from __future__ import annotations

import shutil
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from check_yourself import __tagline__, __version__
from check_yourself.models import AnalysisReport
from check_yourself.visualization.charts import build_chart_html_fragments, embed_plotly_js
from check_yourself.visualization.walkthrough import build_board_aids

_STATIC_FILES = (
    "logo.png",
    "logo-watermark.png",
    "favicon.png",
    "favicon.ico",
    "board.js",
)


def _package_static_dir() -> Traversable:
    return files("check_yourself.reports").joinpath("static")


def copy_report_assets(assets_dir: Path) -> None:
    """Copy brand assets (logo + favicon) into a report's assets directory."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    static = _package_static_dir()
    for name in _STATIC_FILES:
        src = static.joinpath(name)
        with as_file(src) as concrete:
            if concrete.is_file():
                shutil.copy2(concrete, assets_dir / name)


def embed_board_js() -> str:
    """Return offline board / walkthrough JS for self-contained reports."""
    src = _package_static_dir().joinpath("board.js")
    with as_file(src) as concrete:
        return concrete.read_text(encoding="utf-8")


def _asset_url(name: str) -> str | None:
    return f"assets/{name}" if _package_static_dir().joinpath(name).is_file() else None


def render_html_report(
    report: AnalysisReport, username: str, *, include_branding: bool = True
) -> str:
    env = Environment(
        loader=PackageLoader("check_yourself.reports", "templates"),
        autoescape=select_autoescape(["html", "xml", "j2"]),
    )
    template = env.get_template("report.html.j2")
    charts = build_chart_html_fragments(report)
    board_aids = build_board_aids(report)
    board_aids["games_analyzed"] = report.overall.games_analyzed
    return template.render(
        report=report,
        username=username,
        tagline=__tagline__,
        version=__version__,
        plotly_js=embed_plotly_js(),
        plotly_notices=_package_static_dir().joinpath("plotly-basic-NOTICES.txt").read_text(
            encoding="utf-8"
        ),
        board_js=embed_board_js(),
        board_aids=board_aids,
        charts=charts,
        logo_url=_asset_url("logo-watermark.png") if include_branding else None,
        logo_mark_url=_asset_url("logo.png") if include_branding else None,
        favicon_png_url=_asset_url("favicon.png") if include_branding else None,
        favicon_ico_url=_asset_url("favicon.ico") if include_branding else None,
    )


def write_html_report(report: AnalysisReport, username: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    copy_report_assets(path.parent / "assets")
    path.write_text(render_html_report(report, username), encoding="utf-8")
    return path
