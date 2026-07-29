"""Deterministic mock Stockfish adapter for offline tests."""

from __future__ import annotations

import chess

from check_yourself.engine.evaluation import WhiteEval
from check_yourself.engine.stockfish import EngineAnalysis


class MockEngine:
    """Return scripted White-POV evaluations keyed by FEN (without halfmove/fullmove)."""

    def __init__(
        self,
        scores: dict[str, WhiteEval] | None = None,
        *,
        default: WhiteEval | None = None,
    ) -> None:
        self.scores = scores or {}
        self.default = default or WhiteEval(cp=20, mate=None)
        self.calls: list[str] = []

    @staticmethod
    def _key(fen: str) -> str:
        # piece placement + side to move + castling + ep
        parts = fen.split()
        return " ".join(parts[:4])

    def analyse(self, board: chess.Board, *, depth: int | None = None) -> EngineAnalysis:
        fen = board.fen()
        self.calls.append(fen)
        key = self._key(fen)
        white_eval = self.scores.get(key, self.default)
        legal = list(board.legal_moves)
        best = legal[0] if legal else None
        # Only return a legal single-move PV (consecutive legal[:n] is not a PV)
        pv = [best] if best else []
        return EngineAnalysis(
            fen=fen,
            white_eval=white_eval,
            best_move=best,
            pv=pv,
            depth=depth or 8,
        )

    def version(self) -> str:
        return "MockStockfish 0.0"

    def close(self) -> None:
        return None


class ScriptedLossEngine:
    """Engine that returns declining evals so player moves accumulate loss."""

    def __init__(self, start_cp: int = 100, drop_per_player_move: int = 80) -> None:
        self.start_cp = start_cp
        self.drop = drop_per_player_move
        self._player_moves_seen = 0
        self._last_before: int | None = None

    def analyse(self, board: chess.Board, *, depth: int | None = None) -> EngineAnalysis:
        # Alternate: before-move calls vs after-move calls tracked loosely by ply
        # Simpler: evaluation depends on fullmove and whose turn
        # Before player move (player to move): higher eval
        # After player move (opponent to move): lower eval for player side
        legal = list(board.legal_moves)
        best = legal[0] if legal else None
        pv = [best] if best else []

        # Distinct evals per position so preferred-vs-played loss is non-zero
        fen_bias = sum(ord(c) for c in board.board_fen()) % 80
        base = self.start_cp - (30 - len(board.piece_map())) * 5 - fen_bias
        # After White moves, Black to move → White eval reduced for scripted loss
        cp = base - self.drop if board.turn == chess.BLACK else base
        return EngineAnalysis(
            fen=board.fen(),
            white_eval=WhiteEval(cp=cp, mate=None),
            best_move=best,
            pv=pv,
            depth=depth or 8,
        )

    def version(self) -> str:
        return "ScriptedLossEngine 0.0"

    def close(self) -> None:
        return None
