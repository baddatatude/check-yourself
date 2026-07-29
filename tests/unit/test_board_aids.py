"""Board walkthrough / heatmap tests."""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.mock_engine import ScriptedLossEngine
from tests.fixtures.sample_data import SAMPLE_PGN_BLACK, SAMPLE_PGN_RAPID, SAMPLE_PGN_WHITE

from check_yourself.config import AnalysisSettings
from check_yourself.pipeline import analyze_games_offline
from check_yourself.providers.chess_com import parse_pgn_metadata
from check_yourself.visualization.walkthrough import build_board_aids, build_heatmaps


def _metas():
    out = []
    for pgn, end in (
        (SAMPLE_PGN_WHITE, 1),
        (SAMPLE_PGN_BLACK, 2),
        (SAMPLE_PGN_RAPID, 3),
    ):
        meta = parse_pgn_metadata(pgn, username="TestPlayer", end_time=end)
        assert meta is not None
        out.append(meta)
    return out


def test_board_aids_and_html_include_walkthrough(tmp_path: Path) -> None:
    settings = AnalysisSettings(depth=2)
    engine = ScriptedLossEngine(start_cp=300, drop_per_player_move=250)
    report, run_dir = analyze_games_offline(
        "TestPlayer",
        _metas(),
        engine,
        settings=settings,
        output_dir=tmp_path,
    )
    aids = build_board_aids(report)
    assert "sequences" in aids
    assert "heatmaps" in aids
    heat = build_heatmaps(report)
    assert any(heat[k] for k in heat)

    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "Coach walkthrough" in html
    assert "Error heatmaps" in html
    assert "cy-walkthrough" in html
    assert "CheckYourselfBoards.boot" in html
    assert (run_dir / "assets" / "board.js").is_file()
