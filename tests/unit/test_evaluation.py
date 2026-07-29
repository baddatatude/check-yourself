"""Unit tests for evaluation perspective and mate handling."""

from __future__ import annotations

import chess

from check_yourself.engine.evaluation import (
    WhiteEval,
    evaluation_loss_cp,
    preferred_vs_played_loss_cp,
    side_score,
    to_player_evaluation,
)
from check_yourself.models import EvalKind


def test_side_score_centipawns_white_and_black() -> None:
    white = WhiteEval(cp=120, mate=None)
    assert side_score(white, chess.WHITE) == 120
    assert side_score(white, chess.BLACK) == -120


def test_side_score_mate_for_white() -> None:
    white = WhiteEval(cp=None, mate=3)
    assert side_score(white, chess.WHITE) > 90_000
    assert side_score(white, chess.BLACK) < -90_000


def test_side_score_mate_for_black() -> None:
    white = WhiteEval(cp=None, mate=-2)
    assert side_score(white, chess.BLACK) > 90_000
    assert side_score(white, chess.WHITE) < -90_000


def test_to_player_evaluation_flips_for_black() -> None:
    white = WhiteEval(cp=80, mate=None)
    assert to_player_evaluation(white, "white").value == 80
    assert to_player_evaluation(white, "black").value == -80


def test_mate_never_treated_as_ordinary_cp_in_loss() -> None:
    before = WhiteEval(cp=50, mate=None)
    after = WhiteEval(cp=None, mate=-1)  # black mates (bad for white)
    loss = evaluation_loss_cp(before, after, chess.WHITE)
    assert loss > 1000  # mate scale, not ~50cp


def test_black_player_eval_loss_perspective() -> None:
    # From black's perspective: before black was better (white eval -100),
    # after white is better (white eval +200) => black lost ~300
    before = WhiteEval(cp=-100, mate=None)
    after = WhiteEval(cp=200, mate=None)
    loss = evaluation_loss_cp(before, after, chess.BLACK)
    assert loss == 300


def test_preferred_vs_played_loss() -> None:
    after_best = WhiteEval(cp=100, mate=None)
    after_played = WhiteEval(cp=-50, mate=None)
    assert preferred_vs_played_loss_cp(after_best, after_played, chess.WHITE) == 150


def test_mate_evaluation_display_kind() -> None:
    ev = to_player_evaluation(WhiteEval(cp=None, mate=2), "white")
    assert ev.kind == EvalKind.MATE
    assert ev.value == 2
    assert "M2" in ev.display()
