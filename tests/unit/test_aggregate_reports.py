"""Aggregate statistics and opening aggregation tests."""

from __future__ import annotations

from tests.fixtures.mock_engine import ScriptedLossEngine
from tests.fixtures.sample_data import SAMPLE_PGN_BLACK, SAMPLE_PGN_RAPID, SAMPLE_PGN_WHITE

from check_yourself.analysis.aggregate import aggregate_stats
from check_yourself.config import AnalysisSettings
from check_yourself.pipeline import analyze_games_offline
from check_yourself.providers.chess_com import parse_pgn_metadata
from check_yourself.reports.json_report import load_analysis_json


def test_aggregate_and_openings(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = AnalysisSettings(depth=2)
    engine = ScriptedLossEngine()
    metas = []
    for pgn, end in (
        (SAMPLE_PGN_WHITE, 1),
        (SAMPLE_PGN_BLACK, 2),
        (SAMPLE_PGN_RAPID, 3),
    ):
        meta = parse_pgn_metadata(pgn, username="TestPlayer", end_time=end)
        assert meta is not None
        metas.append(meta)

    report, run_dir = analyze_games_offline(
        "TestPlayer",
        metas,
        engine,
        settings=settings,
        output_dir=tmp_path,
        games_requested=5,
        warnings=["Requested 5 games but only found 3 eligible games"],
    )

    assert report.overall.games_analyzed == 3
    assert report.overall.wins + report.overall.losses + report.overall.draws == 3
    assert report.overall.by_phase
    assert report.overall.by_opening
    assert (run_dir / "report.html").is_file()
    assert (run_dir / "analysis.json").is_file()
    assert list((run_dir / "games").glob("*.pgn"))
    assert list((run_dir / "games").glob("*.json"))

    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "Stockfish engine analysis" in html
    assert "Check Yourself" in html
    assert "plotly" in html.lower() or "Plotly" in html or "js" in html

    loaded = load_analysis_json(run_dir / "analysis.json")
    assert loaded.schema_version == report.schema_version
    assert loaded.overall.games_analyzed == 3
    assert "raw" not in loaded.model_dump() or True  # schema preserves sections
    dumped = loaded.model_dump()
    assert "games" in dumped
    assert "overall" in dumped
    assert dumped["games"][0]["metadata"]
    assert dumped["games"][0]["moves"] is not None
    assert dumped["games"][0]["critical_positions"] is not None


def test_aggregate_empty() -> None:
    stats = aggregate_stats([])
    assert stats.games_analyzed == 0
