"""Aggregate statistics and pattern indicators across games."""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

from check_yourself.analysis.game_analyzer import result_for_player
from check_yourself.config import AnalysisSettings
from check_yourself.engine.evaluation import capped_eval_loss_for_acpl
from check_yourself.models import (
    ColorRecord,
    EvalKind,
    GameAnalysisResult,
    GamePhase,
    OpeningStats,
    OverallStats,
    PatternIndicators,
    PhaseStats,
)


def _empty_record() -> ColorRecord:
    return ColorRecord()


def _bump(record: ColorRecord, outcome: str) -> None:
    if outcome == "win":
        record.wins += 1
    elif outcome == "loss":
        record.losses += 1
    elif outcome == "draw":
        record.draws += 1


def aggregate_stats(
    games: list[GameAnalysisResult],
    settings: AnalysisSettings | None = None,
) -> OverallStats:
    settings = settings or AnalysisSettings()
    if not games:
        return OverallStats()

    wins = losses = draws = 0
    by_color: dict[str, ColorRecord] = {
        "white": _empty_record(),
        "black": _empty_record(),
    }
    by_tc: dict[str, ColorRecord] = defaultdict(_empty_record)
    all_losses: list[int] = []
    game_lengths: list[int] = []
    inacc = mist = blun = 0
    critical_total = 0

    phase_loss: dict[str, float] = defaultdict(float)
    phase_moves: dict[str, int] = defaultdict(int)
    phase_mistakes: dict[str, int] = defaultdict(int)
    phase_blunders: dict[str, int] = defaultdict(int)

    opening_data: dict[str, dict[str, Any]] = {}

    for game in games:
        meta = game.metadata
        outcome = result_for_player(meta.result, meta.user_color)
        if outcome == "win":
            wins += 1
        elif outcome == "loss":
            losses += 1
        elif outcome == "draw":
            draws += 1

        _bump(by_color[meta.user_color], outcome)
        _bump(by_tc[meta.time_class], outcome)

        game_lengths.append(len(game.moves))
        critical_total += len(game.critical_positions)
        inacc += game.inaccuracy_count
        mist += game.mistake_count
        blun += game.blunder_count

        for move in game.moves:
            capped = capped_eval_loss_for_acpl(move.eval_loss_cp)
            all_losses.append(capped)
            phase_loss[move.game_phase] += capped
            phase_moves[move.game_phase] += 1
            if move.quality == "mistake":
                phase_mistakes[move.game_phase] += 1
            if move.quality == "blunder":
                phase_blunders[move.game_phase] += 1

        opening_key = meta.opening or meta.eco or "Unknown"
        bucket = opening_data.setdefault(
            opening_key,
            {
                "eco": meta.eco,
                "games": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "losses_cp": [],
                "mistakes": 0,
                "blunders": 0,
            },
        )
        bucket["games"] += 1
        if outcome == "win":
            bucket["wins"] += 1
        elif outcome == "loss":
            bucket["losses"] += 1
        elif outcome == "draw":
            bucket["draws"] += 1
        bucket["losses_cp"].extend(capped_eval_loss_for_acpl(m.eval_loss_cp) for m in game.moves)
        bucket["mistakes"] += game.mistake_count
        bucket["blunders"] += game.blunder_count

    n = len(games)
    total_eval_loss = float(sum(all_losses))
    by_phase: list[PhaseStats] = []
    phase_order: tuple[GamePhase, ...] = ("opening", "middlegame", "endgame")
    for phase in phase_order:
        moves_n = phase_moves[phase]
        total = phase_loss[phase]
        by_phase.append(
            PhaseStats(
                phase=phase,
                move_count=moves_n,
                average_eval_loss=round(total / moves_n, 2) if moves_n else 0.0,
                total_eval_loss=round(total, 2),
                mistake_count=phase_mistakes[phase],
                blunder_count=phase_blunders[phase],
                share_of_total_eval_loss=round(total / total_eval_loss, 4)
                if total_eval_loss
                else 0.0,
            )
        )

    by_opening: list[OpeningStats] = []
    for name, data in sorted(opening_data.items(), key=lambda x: -x[1]["games"]):
        losses_cp: list[int] = data["losses_cp"]
        games_n = int(data["games"])
        by_opening.append(
            OpeningStats(
                opening=name,
                eco=data["eco"],
                games_played=games_n,
                wins=int(data["wins"]),
                losses=int(data["losses"]),
                draws=int(data["draws"]),
                average_centipawn_loss=round(sum(losses_cp) / len(losses_cp), 2)
                if losses_cp
                else 0.0,
                mistakes_per_game=round(data["mistakes"] / games_n, 2),
                blunders_per_game=round(data["blunders"] / games_n, 2),
                small_sample=games_n < 3,
            )
        )

    patterns = compute_patterns(games, settings)

    return OverallStats(
        games_analyzed=n,
        wins=wins,
        losses=losses,
        draws=draws,
        win_rate=round(wins / n, 4) if n else 0.0,
        results_by_color=by_color,
        results_by_time_control=dict(by_tc),
        average_game_length=round(sum(game_lengths) / n, 2) if n else 0.0,
        average_centipawn_loss=round(sum(all_losses) / len(all_losses), 2) if all_losses else 0.0,
        median_centipawn_loss=round(float(median(all_losses)), 2) if all_losses else 0.0,
        inaccuracies_per_game=round(inacc / n, 2),
        mistakes_per_game=round(mist / n, 2),
        blunders_per_game=round(blun / n, 2),
        total_critical_positions=critical_total,
        by_phase=by_phase,
        by_opening=by_opening,
        patterns=patterns,
    )


def compute_patterns(
    games: list[GameAnalysisResult],
    settings: AnalysisSettings,
) -> PatternIndicators:
    notes: list[str] = []
    reached_winning = 0
    winning_spoiled = 0
    equal_lost = 0

    loss_by_move_bucket: dict[str, float] = defaultdict(float)
    loss_by_phase: dict[str, float] = defaultdict(float)
    opening_acpl: dict[str, list[float]] = defaultdict(list)

    for game in games:
        meta = game.metadata
        outcome = result_for_player(meta.result, meta.user_color)
        had_winning = False
        had_equal = False
        peak_eval = -10_000

        for move in game.moves:
            ev = move.eval_after
            cp = ev.value if ev.kind == EvalKind.CP else (10_000 if ev.value > 0 else -10_000)
            peak_eval = max(peak_eval, cp)
            if (ev.kind == EvalKind.MATE and ev.value > 0) or (
                ev.kind == EvalKind.CP and ev.value >= settings.winning_cp
            ):
                had_winning = True
            if ev.kind == EvalKind.CP and abs(ev.value) <= settings.equal_cp:
                had_equal = True

            bucket = _move_bucket(move.fullmove_number)
            capped = capped_eval_loss_for_acpl(move.eval_loss_cp)
            loss_by_move_bucket[bucket] += capped
            loss_by_phase[move.game_phase] += capped

        if had_winning:
            reached_winning += 1
            if outcome in {"draw", "loss"}:
                winning_spoiled += 1
        if had_equal and outcome == "loss" and peak_eval < settings.winning_cp:
            equal_lost += 1

        if game.moves:
            opening_key = meta.opening or meta.eco or "Unknown"
            opening_acpl[opening_key].append(game.average_centipawn_loss)

    move_ranges = [
        {"range": k, "total_eval_loss": round(v, 2)}
        for k, v in sorted(loss_by_move_bucket.items(), key=lambda kv: -kv[1])[:5]
    ]
    phases = [
        {"phase": k, "total_eval_loss": round(v, 2)}
        for k, v in sorted(loss_by_phase.items(), key=lambda kv: -kv[1])
    ]

    high_loss_openings: list[dict[str, Any]] = []
    overall_acpls = [g.average_centipawn_loss for g in games if g.moves]
    overall_mean = sum(overall_acpls) / len(overall_acpls) if overall_acpls else 0.0
    for name, vals in opening_acpl.items():
        if len(vals) < 2:
            continue
        mean = sum(vals) / len(vals)
        if mean > overall_mean * 1.25 and mean - overall_mean >= 15:
            high_loss_openings.append(
                {
                    "opening": name,
                    "games": len(vals),
                    "average_centipawn_loss": round(mean, 2),
                    "baseline_acpl": round(overall_mean, 2),
                    "small_sample": len(vals) < 3,
                }
            )
    high_loss_openings.sort(key=lambda x: -x["average_centipawn_loss"])

    if len(games) < 5:
        notes.append("Small sample: pattern indicators may be noisy with fewer than 5 games.")
    if any(o.get("small_sample") for o in high_loss_openings):
        notes.append("Some openings flagged for high evaluation loss have fewer than 3 games.")

    return PatternIndicators(
        games_reached_winning=reached_winning,
        winning_later_drawn_or_lost=winning_spoiled,
        equal_later_lost=equal_lost,
        largest_loss_move_ranges=move_ranges,
        largest_loss_phases=phases,
        high_loss_openings=high_loss_openings,
        notes=notes,
    )


def _move_bucket(fullmove: int) -> str:
    if fullmove <= 10:
        return "1-10"
    if fullmove <= 20:
        return "11-20"
    if fullmove <= 30:
        return "21-30"
    if fullmove <= 40:
        return "31-40"
    return "41+"
