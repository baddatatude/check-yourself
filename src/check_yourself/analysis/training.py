"""Build exercises using saved scores and legally verifiable moves."""

from __future__ import annotations

import chess

from check_yourself.models import (
    Continuation,
    ContinuationMove,
    ExerciseMove,
    ExerciseSolution,
    MoveAnalysis,
    TrainingExercise,
)


def build_exercise(line: Continuation, move: MoveAnalysis) -> TrainingExercise | None:
    if not line.recommended or not move.eval_loss_cp:
        return None
    board = chess.Board(line.start_fen)
    legal_moves = []
    solutions = [ExerciseSolution(evidence="engine_preferred", moves=line.recommended)]
    preferred = line.recommended[0].uci
    for candidate in sorted(board.legal_moves, key=lambda m: m.uci()):
        san = board.san(candidate)
        uci = candidate.uci()
        legal_moves.append(ExerciseMove(san=san, uci=uci))
        if uci == preferred or not san.endswith("#"):
            continue
        board.push(candidate)
        solutions.append(ExerciseSolution(
            evidence="immediate_checkmate",
            moves=[ContinuationMove(san=san, uci=uci, fen=board.fen())],
        ))
        board.pop()
    return TrainingExercise(
        game_id=move.game_id, ply=move.ply, start_fen=line.start_fen,
        perspective=move.player_color, reference_evaluation=move.eval_before,
        legal_moves=legal_moves, solutions=solutions,
    )
