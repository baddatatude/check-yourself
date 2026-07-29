"""Deterministic game-phase classification.

Method (documented and testable)
--------------------------------
Classify from board features, not move number alone:

1. Count non-king, non-pawn pieces (``N+B+R+Q`` for both sides) as ``pieces``.
2. **Endgame** if either:
   - ``pieces <= 6``, or
   - both queens are off the board and ``pieces <= 8``.
3. **Opening** if not endgame and either:
   - ``fullmove_number <= 10`` and ``pieces >= 12``, or
   - both sides still have some castling rights and ``pieces >= 10`` and
     ``fullmove_number <= 16``.
4. Otherwise **middlegame**.

This is intentionally simple: stable across engines, easy to unit-test, and
good enough for Stage-1 aggregation by phase.
"""

from __future__ import annotations

import chess

from check_yourself.models import GamePhase


def count_minor_major_pieces(board: chess.Board) -> int:
    """Count knights, bishops, rooks, and queens on the board."""
    total = 0
    for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        total += len(board.pieces(piece_type, chess.WHITE))
        total += len(board.pieces(piece_type, chess.BLACK))
    return total


def classify_game_phase(board: chess.Board) -> GamePhase:
    """Return opening / middlegame / endgame for ``board``."""
    pieces = count_minor_major_pieces(board)
    queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(
        board.pieces(chess.QUEEN, chess.BLACK)
    )
    fullmove = board.fullmove_number

    if pieces <= 6 or (queens == 0 and pieces <= 8):
        return "endgame"

    castling = board.castling_rights != 0
    if (fullmove <= 10 and pieces >= 12) or (
        castling and pieces >= 10 and fullmove <= 16
    ):
        return "opening"

    return "middlegame"
