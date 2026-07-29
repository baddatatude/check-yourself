"""Critical position selection and game analysis tests."""

from __future__ import annotations

from tests.fixtures.mock_engine import ScriptedLossEngine
from tests.fixtures.sample_data import SAMPLE_PGN_BLACK, SAMPLE_PGN_WHITE

from check_yourself.analysis.critical_positions import select_critical_positions
from check_yourself.analysis.game_analyzer import GameAnalyzer, result_for_player
from check_yourself.config import AnalysisSettings
from check_yourself.models import (
    CriticalReason,
    EvalKind,
    Evaluation,
    MoveAnalysis,
)
from check_yourself.providers.chess_com import parse_pgn_metadata


def _move(**kwargs: object) -> MoveAnalysis:
    base = dict(
        game_id="g1",
        player_color="white",
        ply=10,
        fullmove_number=5,
        fen_before="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        played_san="e4",
        played_uci="e2e4",
        preferred_uci="e2e4",
        preferred_san="e4",
        principal_variation=["e4", "e5"],
        eval_before=Evaluation(kind=EvalKind.CP, value=100),
        eval_after=Evaluation(kind=EvalKind.CP, value=80),
        eval_loss_cp=20,
        quality="good",
        game_phase="opening",
        result="1-0",
    )
    base.update(kwargs)
    return MoveAnalysis(**base)  # type: ignore[arg-type]


def test_result_for_player() -> None:
    assert result_for_player("1-0", "white") == "win"
    assert result_for_player("1-0", "black") == "loss"
    assert result_for_player("1/2-1/2", "white") == "draw"


def test_critical_winning_to_losing() -> None:
    move = _move(
        eval_before=Evaluation(kind=EvalKind.CP, value=300),
        eval_after=Evaluation(kind=EvalKind.CP, value=-250),
        eval_loss_cp=550,
        quality="blunder",
        preferred_uci="d2d4",
        preferred_san="d4",
        played_san="Qh5",
        played_uci="d1h5",
    )
    selected = select_critical_positions([move], AnalysisSettings(max_critical_positions=3))
    assert len(selected) == 1
    assert CriticalReason.WINNING_OR_EQUAL_TO_LOSING in selected[0].reasons
    assert selected[0].explanation


def test_critical_limits_per_game() -> None:
    moves = [
        _move(
            ply=i,
            fullmove_number=i,
            eval_loss_cp=250 + i,
            quality="blunder",
            eval_before=Evaluation(kind=EvalKind.CP, value=100),
            eval_after=Evaluation(kind=EvalKind.CP, value=-200),
        )
        for i in range(1, 12)
    ]
    settings = AnalysisSettings(max_critical_positions=3)
    selected = select_critical_positions(moves, settings)
    assert len(selected) == 3


def test_game_analyzer_white_and_black() -> None:
    settings = AnalysisSettings(depth=4, max_critical_positions=3)
    engine = ScriptedLossEngine(start_cp=150, drop_per_player_move=90)
    analyzer = GameAnalyzer(engine, settings)

    white_meta = parse_pgn_metadata(SAMPLE_PGN_WHITE, username="TestPlayer", end_time=1)
    black_meta = parse_pgn_metadata(SAMPLE_PGN_BLACK, username="TestPlayer", end_time=2)
    assert white_meta and black_meta

    white_result = analyzer.analyze(white_meta)
    black_result = analyzer.analyze(black_meta)

    assert white_result.metadata.user_color == "white"
    assert black_result.metadata.user_color == "black"
    assert len(white_result.moves) >= 1
    assert len(black_result.moves) >= 1
    assert all(m.player_color == "white" for m in white_result.moves)
    assert all(m.player_color == "black" for m in black_result.moves)
    # Scripted engine creates losses on player moves for white
    assert any(m.eval_loss_cp > 0 for m in white_result.moves)
