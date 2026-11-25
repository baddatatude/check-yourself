"""Local real-Stockfish regression, independent of chess services and LLMs."""

from __future__ import annotations

import shutil

import chess
import pytest

from check_yourself.analysis.game_analyzer import GameAnalyzer
from check_yourself.config import AnalysisSettings
from check_yourself.engine.stockfish import StockfishEngine
from check_yourself.models import EvalKind, GameMetadata


@pytest.mark.integration
def test_stockfish_penalizes_missed_mate_in_one() -> None:
    binary = shutil.which("stockfish")
    if binary is None:
        pytest.skip("Stockfish not on PATH")

    fen = "7k/5Q2/6K1/8/8/8/8/8 w - - 0 1"
    metadata = GameMetadata(
        game_id="missed-mate",
        white="Alice",
        black="Bob",
        user_color="white",
        result="*",
        pgn=f'[SetUp "1"]\n[FEN "{fen}"]\n\n1. Qg8+ *',
    )
    settings = AnalysisSettings(depth=6, _env_file=None)
    with StockfishEngine(binary, depth=settings.depth) as engine:
        row = GameAnalyzer(engine, settings).analyze(metadata).moves[0]
        assert row.preferred_uci is not None
        board = chess.Board(fen)
        board.push_uci(row.preferred_uci)
        assert board.is_checkmate()
        terminal = engine.analyse(board).white_eval
        assert terminal.mate == 0
        assert terminal.terminal_mate_winner == chess.WHITE

    assert row.eval_before.kind == EvalKind.MATE
    assert row.eval_before.mate_for_player is True
    assert row.eval_after.mate_for_player is not True
    assert row.eval_loss_cp >= settings.blunder_threshold
    assert row.quality == "blunder"


@pytest.mark.integration
def test_public_continuations_use_legal_pv_without_invented_scores() -> None:
    from check_yourself import AnalysisOptions, analyze_game

    binary = shutil.which("stockfish")
    if binary is None:
        pytest.skip("Stockfish not on PATH")
    pgn = '[SetUp "1"]\n[FEN "7k/5Q2/6K1/8/8/8/8/8 w - - 0 1"]\n\n1. Qg8+ *'
    game = analyze_game(pgn, options=AnalysisOptions(depth=6)).games[0]
    line = game.continuations[0]
    assert line.ply == 1 and line.start_fen == game.timeline[0].fen
    assert line.actual[0].san == "Qg8+"
    assert line.actual[0].evaluation == game.timeline[1].evaluation
    board = chess.Board(line.start_fen)
    board.push_uci(line.recommended[0].uci)
    assert board.is_checkmate() and line.recommended[0].evaluation is None

    exercise = game.exercises[0]
    assert exercise.start_fen == line.start_fen
    assert exercise.reference_evaluation.mate_sign == 1
    assert len(exercise.solutions) > 1
    assert {m.uci() for m in chess.Board(line.start_fen).legal_moves} == {
        move.uci for move in exercise.legal_moves
    }
    for solution in exercise.solutions:
        board = chess.Board(exercise.start_fen)
        board.push_uci(solution.moves[0].uci)
        assert board.is_checkmate()
