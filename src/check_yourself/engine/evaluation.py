"""Evaluation normalization and centipawn-loss helpers.

All Stockfish scores are read in White's perspective, then reprojected to the
requested player's perspective before loss calculations.

Mate scores are never treated as ordinary centipawn values. They use a synthetic
scale of ±100_000 adjusted by mate distance so closer mates rank higher.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess
import chess.engine

from check_yourself.models import EvalKind, Evaluation, PlayerColor

MATE_SCORE = 100_000

# Cap used only for ACPL / phase / opening *averages*.
# Raw per-move ``eval_loss_cp`` keeps the mate-scale loss so quality labels and
# critical-position ranking still treat mate blunders as catastrophic.
ACPL_LOSS_CAP_CP = 1000


def capped_eval_loss_for_acpl(eval_loss_cp: int, *, cap: int = ACPL_LOSS_CAP_CP) -> int:
    """Clamp a move's eval loss for human-readable average CPL statistics."""
    return min(max(0, int(eval_loss_cp)), cap)


@dataclass(frozen=True)
class WhiteEval:
    """Raw engine score in White's perspective."""

    cp: int | None = None
    mate: int | None = None
    terminal_mate_winner: chess.Color | None = None

    @property
    def is_mate(self) -> bool:
        return self.mate is not None


def side_score(white: WhiteEval, color: chess.Color) -> float:
    """Higher is better for ``color``. Mate dominates centipawns."""
    if white.mate is not None:
        mate = white.mate
        if mate > 0:
            # White mates in ``mate``
            return float(MATE_SCORE - mate) if color == chess.WHITE else float(-MATE_SCORE + mate)
        if mate < 0:
            # Black mates in ``-mate``
            n = -mate
            return float(-MATE_SCORE + n) if color == chess.WHITE else float(MATE_SCORE - n)
        if white.terminal_mate_winner is not None:
            return float(MATE_SCORE if color == white.terminal_mate_winner else -MATE_SCORE)
        return 0.0
    cp = white.cp if white.cp is not None else 0
    return float(cp) if color == chess.WHITE else float(-cp)


def to_player_evaluation(white: WhiteEval, player: PlayerColor) -> Evaluation:
    """Convert White-POV engine score into the player's perspective."""
    if white.mate is not None:
        value = white.mate if player == "white" else -white.mate
        mover = chess.WHITE if player == "white" else chess.BLACK
        score = side_score(white, mover)
        return Evaluation(
            kind=EvalKind.MATE,
            value=value,
            white_cp=None,
            white_mate=white.mate,
            mate_for_player=score > 0 if score else None,
        )
    cp_white = white.cp if white.cp is not None else 0
    value = cp_white if player == "white" else -cp_white
    return Evaluation(
        kind=EvalKind.CP,
        value=value,
        white_cp=cp_white,
        white_mate=None,
    )


def evaluation_loss_cp(
    before: WhiteEval,
    after: WhiteEval,
    mover: chess.Color,
) -> int:
    """Centipawn loss for the mover: how much worse the position became.

    Uses player-perspective side scores. Mate transitions are handled via the
    synthetic mate scale, never by casting mate distance into raw centipawns.
    """
    before_s = side_score(before, mover)
    after_s = side_score(after, mover)
    return max(0, int(round(before_s - after_s)))


def preferred_vs_played_loss_cp(
    after_best: WhiteEval,
    after_played: WhiteEval,
    mover: chess.Color,
) -> int:
    """Loss relative to Stockfish's preferred continuation."""
    best_s = side_score(after_best, mover)
    played_s = side_score(after_played, mover)
    return max(0, int(round(best_s - played_s)))


def parse_score_white(score: chess.engine.PovScore) -> WhiteEval:
    """Extract White-POV cp/mate, keeping the winner of a terminal mate."""
    white = score.white()
    mate = white.mate()
    if mate is not None:
        winner = None
        if mate == 0:
            winner = chess.WHITE if white == chess.engine.MateGiven else chess.BLACK
        return WhiteEval(mate=mate, terminal_mate_winner=winner)
    return WhiteEval(cp=white.score())
