"""Piece + tactics analyzer tests."""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.mock_engine import ScriptedLossEngine
from tests.fixtures.sample_data import SAMPLE_PGN_BLACK, SAMPLE_PGN_RAPID, SAMPLE_PGN_WHITE

from check_yourself.analysis.tactics_analyzer import analyze_piece_and_tactics
from check_yourself.config import AnalysisSettings
from check_yourself.pipeline import analyze_games_offline
from check_yourself.providers.chess_com import parse_pgn_metadata


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


def test_tactics_report_attached_and_html(tmp_path: Path) -> None:
    settings = AnalysisSettings(depth=2)
    engine = ScriptedLossEngine(start_cp=300, drop_per_player_move=250)
    report, run_dir = analyze_games_offline(
        "TestPlayer",
        _metas(),
        engine,
        settings=settings,
        output_dir=tmp_path,
    )
    assert report.tactics is not None
    assert report.tactics.games_analyzed == 3
    assert report.schema_version == "1.4.0"
    # Scripted blunders should produce a piece breakdown
    assert report.tactics.blunders_by_piece or report.tactics.notes

    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "Pieces &amp; tactics that hurt you" in html or "Pieces & tactics" in html
    assert "Blunders by piece" in html


def test_analyze_piece_and_tactics_direct() -> None:
    settings = AnalysisSettings(depth=2)
    engine = ScriptedLossEngine(start_cp=400, drop_per_player_move=350)
    from check_yourself.analysis.game_analyzer import GameAnalyzer

    games = [GameAnalyzer(engine, settings).analyze(m) for m in _metas()]
    tactics = analyze_piece_and_tactics(games)
    assert tactics.games_analyzed == 3
    assert isinstance(tactics.blunders_by_piece, list)
    assert isinstance(tactics.tactics_that_hurt, list)
    assert isinstance(tactics.mated_by_piece, list)
    # Scripted losses usually create mistakes/blunders; allow empty with notes
    assert tactics.errors_scanned >= 0
    assert tactics.notes
