"""Critical-position selection for instructive mistakes and turning points."""

from __future__ import annotations

from check_yourself.config import AnalysisSettings
from check_yourself.models import (
    CriticalPosition,
    CriticalReason,
    EvalKind,
    MoveAnalysis,
)


def _is_winning(eval_cp_or_mate: MoveAnalysis, *, before: bool, settings: AnalysisSettings) -> bool:
    ev = eval_cp_or_mate.eval_before if before else eval_cp_or_mate.eval_after
    if ev.kind == EvalKind.MATE:
        return ev.value > 0
    return ev.value >= settings.winning_cp


def _is_equal(move: MoveAnalysis, *, before: bool, settings: AnalysisSettings) -> bool:
    ev = move.eval_before if before else move.eval_after
    if ev.kind == EvalKind.MATE:
        return False
    return abs(ev.value) <= settings.equal_cp


def _is_losing(move: MoveAnalysis, *, before: bool, settings: AnalysisSettings) -> bool:
    ev = move.eval_before if before else move.eval_after
    if ev.kind == EvalKind.MATE:
        return ev.value < 0
    return ev.value <= -settings.losing_cp


def _reasons_for(move: MoveAnalysis, settings: AnalysisSettings) -> list[CriticalReason]:
    reasons: list[CriticalReason] = []

    if move.eval_loss_cp >= settings.mistake_threshold:
        reasons.append(CriticalReason.LARGEST_EVAL_LOSS)

    if _is_winning(move, before=True, settings=settings) and _is_equal(
        move, before=False, settings=settings
    ):
        reasons.append(CriticalReason.WINNING_TO_EQUAL)

    if (
        _is_winning(move, before=True, settings=settings)
        or _is_equal(move, before=True, settings=settings)
    ) and _is_losing(move, before=False, settings=settings):
        reasons.append(CriticalReason.WINNING_OR_EQUAL_TO_LOSING)

    # Missed win: was not clearly winning, but preferred line mates / wins and played doesn't
    if (
        move.preferred_uci
        and move.preferred_uci != move.played_uci
        and move.eval_before.kind == EvalKind.CP
        and move.eval_before.value < settings.winning_cp
        and move.eval_loss_cp >= settings.mistake_threshold
        and (
            (
                move.eval_before.kind == EvalKind.CP
                and move.eval_loss_cp >= settings.blunder_threshold
            )
            or move.mate_after is not None
            and (move.mate_after or 0) < 0
        )
    ):
        reasons.append(CriticalReason.MISSED_WIN)

    if (
        _is_losing(move, before=True, settings=settings) is False
        and move.eval_loss_cp >= settings.mistake_threshold
        and _is_losing(move, before=False, settings=settings)
        and CriticalReason.WINNING_OR_EQUAL_TO_LOSING not in reasons
    ):
        reasons.append(CriticalReason.MISSED_DEFENSE)

    before_mate = move.eval_before.kind == EvalKind.MATE and move.eval_before.value > 0
    after_mated = move.eval_after.kind == EvalKind.MATE and move.eval_after.value < 0
    introduced_mate_against = (
        move.eval_before.kind == EvalKind.CP
        and move.eval_after.kind == EvalKind.MATE
        and move.eval_after.value < 0
    )
    lost_forced_mate = (
        before_mate
        and move.eval_after.kind == EvalKind.CP
        and move.eval_after.value < settings.winning_cp
    )
    if after_mated or introduced_mate_against or lost_forced_mate:
        reasons.append(CriticalReason.INTRODUCED_MATE)

    # Large swing counts as turning point
    if move.eval_loss_cp >= settings.blunder_threshold:
        reasons.append(CriticalReason.TURNING_POINT)

    return reasons


def _importance(move: MoveAnalysis, reasons: list[CriticalReason]) -> float:
    score = float(move.eval_loss_cp)
    weights = {
        CriticalReason.INTRODUCED_MATE: 500,
        CriticalReason.WINNING_OR_EQUAL_TO_LOSING: 300,
        CriticalReason.WINNING_TO_EQUAL: 200,
        CriticalReason.MISSED_WIN: 250,
        CriticalReason.MISSED_DEFENSE: 180,
        CriticalReason.TURNING_POINT: 150,
        CriticalReason.LARGEST_EVAL_LOSS: 50,
    }
    for reason in reasons:
        score += weights.get(reason, 0)
    return score


def _explanation(move: MoveAnalysis, reasons: list[CriticalReason]) -> str:
    parts = [
        f"Move {move.fullmove_number} ({move.played_san}): "
        f"evaluation loss {move.eval_loss_cp} cp "
        f"({move.eval_before.display()} → {move.eval_after.display()})."
    ]
    labels = {
        CriticalReason.LARGEST_EVAL_LOSS: (
            "Large evaluation loss relative to the prior position."
        ),
        CriticalReason.WINNING_TO_EQUAL: (
            "A clearly winning position became approximately equal."
        ),
        CriticalReason.WINNING_OR_EQUAL_TO_LOSING: (
            "A winning or equal position became losing."
        ),
        CriticalReason.MISSED_WIN: (
            "A significant winning opportunity appears to have been missed."
        ),
        CriticalReason.MISSED_DEFENSE: (
            "A defensive resource was missed and the position became losing."
        ),
        CriticalReason.INTRODUCED_MATE: (
            "The move introduced or allowed a forced mate."
        ),
        CriticalReason.TURNING_POINT: (
            "Major turning point based on evaluation swing."
        ),
    }
    for reason in reasons:
        parts.append(labels[reason])
    if move.preferred_san:
        parts.append(f"Stockfish preferred {move.preferred_san} over {move.played_san}.")
    return " ".join(parts)


def select_critical_positions(
    moves: list[MoveAnalysis],
    settings: AnalysisSettings | None = None,
) -> list[CriticalPosition]:
    """Select a limited set of instructive positions, ranked by importance."""
    settings = settings or AnalysisSettings()
    candidates: list[CriticalPosition] = []

    for move in moves:
        # Skip trivial fluctuations
        if move.eval_loss_cp < settings.inaccuracy_threshold and move.quality not in {
            "mistake",
            "blunder",
        }:
            # Still consider mate introductions even with lower threshold loss
            reasons_probe = _reasons_for(move, settings)
            if CriticalReason.INTRODUCED_MATE not in reasons_probe:
                continue

        reasons = _reasons_for(move, settings)
        if not reasons:
            continue

        candidates.append(
            CriticalPosition(
                game_id=move.game_id,
                ply=move.ply,
                fullmove_number=move.fullmove_number,
                fen=move.fen_before,
                player_color=move.player_color,
                played_san=move.played_san,
                played_uci=move.played_uci,
                preferred_san=move.preferred_san,
                preferred_uci=move.preferred_uci,
                principal_variation=list(move.principal_variation),
                eval_before=move.eval_before,
                eval_after=move.eval_after,
                eval_loss_cp=move.eval_loss_cp,
                quality=move.quality,
                game_phase=move.game_phase,
                reasons=reasons,
                importance_score=_importance(move, reasons),
                explanation=_explanation(move, reasons),
            )
        )

    candidates.sort(key=lambda c: (-c.importance_score, c.ply))

    # Prefer diversity of reasons while keeping top-N
    selected: list[CriticalPosition] = []
    seen_plies: set[int] = set()
    for cand in candidates:
        if cand.ply in seen_plies:
            continue
        selected.append(cand)
        seen_plies.add(cand.ply)
        if len(selected) >= settings.max_critical_positions:
            break
    return selected
