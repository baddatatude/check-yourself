"""Regression tests for terminal scores, player perspective and PGN replay."""

from __future__ import annotations

from dataclasses import replace

import chess
import chess.engine
import pytest
from tests.fixtures.mock_engine import MockEngine

from check_yourself.analysis.game_analyzer import GameAnalyzer
from check_yourself.config import AnalysisSettings
from check_yourself.engine.evaluation import (
    MATE_SCORE,
    WhiteEval,
    evaluation_loss_cp,
    parse_score_white,
    side_score,
    to_player_evaluation,
)
from check_yourself.engine.stockfish import EngineAnalysis
from check_yourself.models import CriticalReason, GameMetadata, PlayerColor

MATE_IN_ONE = "7k/5Q2/6K1/8/8/8/8/8 w - - 0 1"


class PreferredMoveEngine(MockEngine):
    """Use a specific root move while keeping child scores deterministic."""

    def __init__(self, root: chess.Board, preferred: str, scores: dict[str, WhiteEval]):
        super().__init__(scores=scores)
        self.root_fen = root.fen()
        self.preferred = root.parse_san(preferred)
        self.history_lengths: list[int] = []

    def analyse(self, board: chess.Board, *, depth: int | None = None) -> EngineAnalysis:
        result = super().analyse(board, depth=depth)
        self.history_lengths.append(len(board.move_stack))
        if board.fen() == self.root_fen:
            return replace(result, best_move=self.preferred, pv=[self.preferred])
        return result


def setup_game(board: chess.Board, san: str, player: PlayerColor) -> GameMetadata:
    pgn = f'[SetUp "1"]\n[FEN "{board.fen()}"]\n\n{board.fullmove_number}. {san} *'
    return GameMetadata(
        game_id="synthetic", white="Alice", black="Bob", user_color=player, result="*", pgn=pgn
    )


@pytest.mark.parametrize("winner", [chess.WHITE, chess.BLACK])
def test_terminal_mate_keeps_winner_at_distance_zero(winner: chess.Color) -> None:
    raw = chess.engine.PovScore(chess.engine.Mate(0), not winner)
    normalized = parse_score_white(raw)
    assert normalized.mate == 0
    assert normalized.terminal_mate_winner == winner
    assert side_score(normalized, winner) == MATE_SCORE
    assert side_score(normalized, not winner) == -MATE_SCORE
    for player in ("white", "black"):
        result = to_player_evaluation(normalized, player)
        won = (player == "white") == winner
        assert result.value == 0
        assert result.mate_for_player is won
        assert result.display() == ("+M0" if won else "-M0")
        assert result.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("player", ["white", "black"])
def test_missing_mate_and_equivalent_mate(player: PlayerColor) -> None:
    root = chess.Board(MATE_IN_ONE)
    winner = player == "white"
    preferred, missed, equivalent = "Qg7#", "Qg8+", "Qf8#"
    if not winner:
        root = root.mirror()
        preferred, missed, equivalent = "Qg2#", "Qg1+", "Qf1#"

    def score_key(san: str) -> str:
        child = root.copy()
        child.push_san(san)
        return MockEngine._key(child.fen())

    terminal = parse_score_white(chess.engine.PovScore(chess.engine.Mate(0), not winner))
    engine = PreferredMoveEngine(root, preferred, {
        MockEngine._key(root.fen()): WhiteEval(mate=1 if winner else -1),
        score_key(preferred): terminal,
        score_key(missed): WhiteEval(cp=18 if winner else -18),
        score_key(equivalent): terminal,
    })
    analyzer = GameAnalyzer(engine, AnalysisSettings(_env_file=None))
    lost = analyzer.analyze(setup_game(root, missed, player))
    assert lost.moves[0].eval_loss_cp == MATE_SCORE - 18
    assert lost.moves[0].quality == "blunder"
    assert CriticalReason.INTRODUCED_MATE in lost.critical_positions[0].reasons

    for mating_move in (preferred, equivalent):
        same = analyzer.analyze(setup_game(root, mating_move, player))
        assert same.moves[0].eval_loss_cp == 0
        assert same.moves[0].quality == "best"
        assert same.moves[0].eval_after.display() == "+M0"
        assert same.eval_graph[0]["eval"] == 1000


@pytest.mark.parametrize("mover", [chess.WHITE, chess.BLACK])
def test_mate_and_centipawn_score_transitions(mover: chess.Color) -> None:
    sign = 1 if mover else -1
    ordinary = parse_score_white(chess.engine.PovScore(chess.engine.Cp(55), mover))
    assert ordinary.cp == sign * 55
    own_mate = WhiteEval(mate=sign * 2)
    opponent_mate = WhiteEval(mate=-sign)
    assert evaluation_loss_cp(ordinary, opponent_mate, mover) == MATE_SCORE + 54
    assert evaluation_loss_cp(own_mate, ordinary, mover) == MATE_SCORE - 57
    assert evaluation_loss_cp(ordinary, own_mate, mover) == 0


@pytest.mark.parametrize(
    ("loss", "quality"),
    [
        (0, "best"), (1, "excellent"), (10, "excellent"), (11, "good"),
        (25, "good"), (26, "inaccuracy"), (50, "inaccuracy"), (51, "mistake"),
        (100, "mistake"), (101, "mistake"), (199, "mistake"), (200, "blunder"),
        (201, "blunder"),
    ],
)
def test_move_classification_boundaries(loss: int, quality: str) -> None:
    root = chess.Board()
    scores = {}
    for san, cp in (("e4", 100), ("d4", 100 - loss)):
        child = root.copy()
        child.push_san(san)
        scores[MockEngine._key(child.fen())] = WhiteEval(cp=cp)
    result = GameAnalyzer(PreferredMoveEngine(root, "e4", scores)).analyze(
        setup_game(root, "d4", "white")
    )
    assert result.moves[0].eval_loss_cp == loss
    assert result.moves[0].quality == quality


def test_player_ply_alignment_and_history_when_allowing_mate() -> None:
    root = chess.Board()
    root.push_san("f3")
    root.push_san("e5")
    child = root.copy()
    child.push_san("g4")
    engine = PreferredMoveEngine(root, "e4", {MockEngine._key(child.fen()): WhiteEval(mate=-1)})
    pgn = "1. f3 e5 2. g4 Qh4# 0-1"
    meta = GameMetadata(
        game_id="fools", white="Alice", black="Bob", result="0-1", user_color="white", pgn=pgn
    )
    analysis = GameAnalyzer(engine).analyze(meta)
    assert [(row.ply, row.fullmove_number, row.played_uci) for row in analysis.moves] == [
        (1, 1, "f2f3"), (3, 2, "g2g4"),
    ]
    second = analysis.moves[1]
    assert second.fen_before == root.fen()
    assert second.preferred_san == "e4"
    assert second.eval_after.display() == "-M1"
    assert analysis.eval_graph[1]["eval"] == -1000
    assert second.quality == "blunder"
    assert CriticalReason.INTRODUCED_MATE in analysis.critical_positions[0].reasons
    assert engine.history_lengths[-3:] == [2, 3, 3]
