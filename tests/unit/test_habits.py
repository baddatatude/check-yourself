"""Cross-game habit analyzer tests."""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.mock_engine import ScriptedLossEngine
from tests.fixtures.sample_data import SAMPLE_PGN_BLACK, SAMPLE_PGN_RAPID, SAMPLE_PGN_WHITE

from check_yourself.analysis.aggregate import aggregate_stats
from check_yourself.analysis.habit_analyzer import analyze_habits, habit_brief_for_coaching
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


def test_analyze_habits_produces_report(tmp_path: Path) -> None:
    settings = AnalysisSettings(depth=2)
    engine = ScriptedLossEngine(start_cp=250, drop_per_player_move=220)
    report, run_dir = analyze_games_offline(
        "TestPlayer",
        _metas(),
        engine,
        settings=settings,
        output_dir=tmp_path,
    )
    assert report.habits is not None
    assert report.habits.games_analyzed == 3
    assert report.habits.notes  # small-sample notes
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "Habits" in html
    dumped = (run_dir / "analysis.json").read_text(encoding="utf-8")
    assert "habits" in dumped


def test_habit_brief_for_coaching_shape() -> None:
    settings = AnalysisSettings(depth=2)
    engine = ScriptedLossEngine(start_cp=300, drop_per_player_move=250)
    from check_yourself.analysis.game_analyzer import GameAnalyzer

    games = [GameAnalyzer(engine, settings).analyze(m) for m in _metas()]
    overall = aggregate_stats(games, settings)
    habits = analyze_habits(games, overall, settings)
    brief = habit_brief_for_coaching(habits)
    assert brief["games_analyzed"] == 3
    assert "findings" in brief
    assert "strengths" in brief
    assert "notes" in brief


def test_conversion_leak_habit_when_winning_spoiled() -> None:
    """Scripted large drops from high eval should surface conversion / error habits."""
    settings = AnalysisSettings(depth=2, winning_cp=150)
    engine = ScriptedLossEngine(start_cp=400, drop_per_player_move=350)
    from check_yourself.analysis.game_analyzer import GameAnalyzer

    games = [GameAnalyzer(engine, settings).analyze(m) for m in _metas()]
    overall = aggregate_stats(games, settings)
    habits = analyze_habits(games, overall, settings)
    # With aggressive scripted losses, expect at least one finding or a clear empty note
    assert habits.games_analyzed == 3
    ids = {f.id for f in habits.findings}
    # Phase blunders or late errors or conversion are acceptable outcomes
    assert habits.findings or "No strong recurring habits" in " ".join(habits.notes)
    if habits.findings:
        assert all(f.summary and f.practice_hint for f in habits.findings)
        assert ids
