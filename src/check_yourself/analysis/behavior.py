"""Cautious, descriptive cross-game measurements from recorded evaluations."""

from __future__ import annotations

from datetime import date

from check_yourself.engine.evaluation import capped_eval_loss_for_acpl
from check_yourself.models import (
    BehaviorSummary,
    ColorPerformance,
    DatedPerformance,
    EvalKind,
    GameAnalysisResult,
    PlayerColor,
)


def summarize_behavior(
    games: list[GameAnalysisResult], *, advantage_threshold_cp: int,
) -> BehaviorSummary:
    colors: tuple[PlayerColor, ...] = ("white", "black")
    by_color = []
    for color in colors:
        selected = [game for game in games if game.metadata.user_color == color]
        moves = [move for game in selected for move in game.moves]
        count = len(moves)
        total_loss = sum(capped_eval_loss_for_acpl(move.eval_loss_cp) for move in moves)
        by_color.append(ColorPerformance(
            color=color, games=len(selected), moves=count,
            capped_acpl=round(total_loss / count, 2) if count else None,
        ))

    dated = []
    missed = allowed = known = advantageous = converted = scored = 0
    for game in games:
        meta = game.metadata
        scored += len(game.moves)
        if meta.date:
            try:
                played_on = date.fromisoformat(meta.date.replace(".", "-"))
            except ValueError:
                pass
            else:
                dated.append(DatedPerformance(
                    game_id=meta.game_id, played_on=played_on, color=meta.user_color,
                    moves=len(game.moves),
                    capped_acpl=game.average_centipawn_loss if game.moves else None,
                ))
        for move in game.moves:
            if move.eval_before.mate_sign > 0 and move.eval_after.mate_sign <= 0:
                missed += 1
            if move.eval_before.mate_sign >= 0 and move.eval_after.mate_sign < 0:
                allowed += 1
        if meta.result not in {"1-0", "0-1", "1/2-1/2"}:
            continue
        known += 1
        # Use positions where the player had a move, so a final result cannot
        # create its own evidence of a convertible advantage.
        if any(move.eval_before.mate_sign > 0 or (
            move.eval_before.kind == EvalKind.CP
            and move.eval_before.value >= advantage_threshold_cp
        ) for move in game.moves):
            advantageous += 1
            won = "1-0" if meta.user_color == "white" else "0-1"
            converted += int(meta.result == won)

    return BehaviorSummary(
        games=len(games), scored_moves=scored, by_color=by_color, missed_mates=missed,
        allowed_mates=allowed, known_result_games=known, advantageous_games=advantageous,
        converted_advantageous_games=converted, advantage_threshold_cp=advantage_threshold_cp,
        dated_games=sorted(dated, key=lambda entry: entry.played_on),
    )
