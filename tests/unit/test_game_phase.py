"""Game-phase classification tests."""

from __future__ import annotations

import chess

from check_yourself.analysis.game_phase import classify_game_phase, count_minor_major_pieces


def test_starting_position_is_opening() -> None:
    board = chess.Board()
    assert classify_game_phase(board) == "opening"
    assert count_minor_major_pieces(board) == 14


def test_endgame_few_pieces() -> None:
    # King and pawns + one rook each
    board = chess.Board("4k3/8/8/8/8/8/4P3/4K2R w K - 0 40")
    assert classify_game_phase(board) == "endgame"


def test_middlegame_dense_position() -> None:
    board = chess.Board(
        "r1bq1rk1/pp2ppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/2KR1B1R w - - 0 12"
    )
    # fullmove 12, still many pieces, no castling rights for white? white castled long gone
    # castling rights empty, fullmove 12, pieces high -> middlegame
    assert classify_game_phase(board) == "middlegame"


def test_no_queens_low_pieces_endgame() -> None:
    board = chess.Board("4k3/5ppp/8/8/8/8/5PPP/4K2R w K - 0 30")
    assert classify_game_phase(board) == "endgame"
