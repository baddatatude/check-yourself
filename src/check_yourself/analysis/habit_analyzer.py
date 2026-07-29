"""Deterministic cross-game habit / weakness analysis."""

from __future__ import annotations

from collections import defaultdict

from check_yourself.analysis.game_analyzer import result_for_player
from check_yourself.config import AnalysisSettings
from check_yourself.models import (
    CriticalPosition,
    CriticalReason,
    EvalKind,
    GameAnalysisResult,
    HabitExample,
    HabitFinding,
    HabitReport,
    HabitSeverity,
    MoveAnalysis,
    OverallStats,
)


def _example_from_move(move: MoveAnalysis, *, note: str) -> HabitExample:
    return HabitExample(
        game_id=move.game_id,
        ply=move.ply,
        fullmove_number=move.fullmove_number,
        fen=move.fen_before,
        played_san=move.played_san,
        preferred_san=move.preferred_san,
        played_uci=move.played_uci,
        preferred_uci=move.preferred_uci,
        eval_loss_cp=move.eval_loss_cp,
        quality=move.quality,
        phase=move.game_phase,
        note=note,
        player_color=move.player_color,
    )


def _example_from_critical(cp: CriticalPosition, *, note: str | None = None) -> HabitExample:
    return HabitExample(
        game_id=cp.game_id,
        ply=cp.ply,
        fullmove_number=cp.fullmove_number,
        fen=cp.fen,
        played_san=cp.played_san,
        preferred_san=cp.preferred_san,
        played_uci=cp.played_uci,
        preferred_uci=cp.preferred_uci,
        eval_loss_cp=cp.eval_loss_cp,
        quality=cp.quality,
        phase=cp.game_phase,
        note=note or cp.explanation,
        player_color=cp.player_color,
    )


def _severity_from_rate(rate: float, *, high: float = 0.4, medium: float = 0.2) -> HabitSeverity:
    if rate >= high:
        return HabitSeverity.HIGH
    if rate >= medium:
        return HabitSeverity.MEDIUM
    return HabitSeverity.LOW


def _top_examples(examples: list[HabitExample], limit: int = 3) -> list[HabitExample]:
    return sorted(examples, key=lambda e: -e.eval_loss_cp)[:limit]


def analyze_habits(
    games: list[GameAnalysisResult],
    overall: OverallStats,
    settings: AnalysisSettings | None = None,
) -> HabitReport:
    """Build a habit brief from Stockfish-backed analysis (no LLM)."""
    settings = settings or AnalysisSettings()
    n = len(games)
    notes: list[str] = []
    findings: list[HabitFinding] = []
    strengths: list[str] = []

    if n == 0:
        return HabitReport(games_analyzed=0, notes=["No games available for habit analysis."])

    if n < 5:
        notes.append("Small sample: habits may be noisy with fewer than 5 games.")
    if n < 10:
        notes.append("For stronger habit signals, analyze 20+ recent games.")

    patterns = overall.patterns

    # --- Conversion leaks ---
    if patterns.games_reached_winning > 0:
        rate = patterns.winning_later_drawn_or_lost / patterns.games_reached_winning
        examples: list[HabitExample] = []
        for game in games:
            outcome = result_for_player(game.metadata.result, game.metadata.user_color)
            if outcome not in {"draw", "loss"}:
                continue
            for cp in game.critical_positions:
                if CriticalReason.WINNING_OR_EQUAL_TO_LOSING in cp.reasons or (
                    CriticalReason.MISSED_WIN in cp.reasons
                ):
                    examples.append(_example_from_critical(cp))
            if not any(e.game_id == game.metadata.game_id for e in examples):
                # Fall back to largest blunder in spoiled winning games
                blunders = [m for m in game.moves if m.quality == "blunder"]
                if blunders:
                    worst = max(blunders, key=lambda m: m.eval_loss_cp)
                    examples.append(
                        _example_from_move(
                            worst,
                            note="Large evaluation drop in a game that reached a winning position.",
                        )
                    )
        thin = patterns.games_reached_winning < 3
        if patterns.winning_later_drawn_or_lost > 0 and (rate >= 0.2 or thin is False):
            findings.append(
                HabitFinding(
                    id="conversion_leaks",
                    title="Struggling to convert winning positions",
                    severity=_severity_from_rate(rate),
                    evidence_count=patterns.winning_later_drawn_or_lost,
                    games_affected=patterns.winning_later_drawn_or_lost,
                    rate=round(rate, 4),
                    summary=(
                        f"Reached a clearly winning position in "
                        f"{patterns.games_reached_winning}/{n} games, but "
                        f"{patterns.winning_later_drawn_or_lost} of those later drew or lost "
                        f"({rate * 100:.0f}%)."
                    ),
                    practice_hint=(
                        "When clearly better, simplify: trade into a clean endgame, "
                        "avoid unnecessary complications, and check forcing moves first."
                    ),
                    examples=_top_examples(examples),
                    thin_evidence=thin,
                )
            )

    # --- Equal positions collapsed ---
    if patterns.equal_later_lost > 0:
        rate = patterns.equal_later_lost / n
        examples = []
        for game in games:
            outcome = result_for_player(game.metadata.result, game.metadata.user_color)
            if outcome != "loss":
                continue
            candidates = [
                m
                for m in game.moves
                if m.quality in {"mistake", "blunder"}
                and m.eval_before.kind == EvalKind.CP
                and abs(m.eval_before.value) <= settings.equal_cp
            ]
            if candidates:
                worst = max(candidates, key=lambda m: m.eval_loss_cp)
                examples.append(
                    _example_from_move(
                        worst,
                        note="Error from an approximately equal position that ended in a loss.",
                    )
                )
        findings.append(
            HabitFinding(
                id="equal_to_lost",
                title="Losing from roughly equal positions",
                severity=_severity_from_rate(rate, high=0.35, medium=0.15),
                evidence_count=patterns.equal_later_lost,
                games_affected=patterns.equal_later_lost,
                rate=round(rate, 4),
                summary=(
                    f"In {patterns.equal_later_lost}/{n} games, the position was about equal "
                    f"at some point and the game was later lost."
                ),
                practice_hint=(
                    "In quiet equal positions, prioritize piece activity and prophylaxis: "
                    "ask what your opponent wants before creating weaknesses."
                ),
                examples=_top_examples(examples),
                thin_evidence=patterns.equal_later_lost < 2,
            )
        )

    # --- Phase-concentrated errors ---
    total_blunders = sum(g.blunder_count for g in games)
    if total_blunders > 0:
        phase_blunders: dict[str, list[HabitExample]] = defaultdict(list)
        phase_counts: dict[str, int] = defaultdict(int)
        for game in games:
            for move in game.moves:
                if move.quality != "blunder":
                    continue
                phase_counts[move.game_phase] += 1
                phase_blunders[move.game_phase].append(
                    _example_from_move(move, note=f"Blunder in the {move.game_phase}.")
                )
        for phase, count in sorted(phase_counts.items(), key=lambda kv: -kv[1]):
            rate = count / total_blunders
            if rate < 0.4 or count < 2:
                continue
            findings.append(
                HabitFinding(
                    id=f"blunders_{phase}",
                    title=f"Blunders concentrated in the {phase}",
                    severity=_severity_from_rate(rate, high=0.55, medium=0.4),
                    evidence_count=count,
                    games_affected=len({e.game_id for e in phase_blunders[phase]}),
                    rate=round(rate, 4),
                    summary=(
                        f"{count}/{total_blunders} blunders ({rate * 100:.0f}%) occurred "
                        f"in the {phase}."
                    ),
                    practice_hint=_phase_practice_hint(phase),
                    examples=_top_examples(phase_blunders[phase]),
                    thin_evidence=count < 3,
                )
            )

    # --- Late-game / time-pressure proxy ---
    late_errors: list[HabitExample] = []
    all_errors = 0
    for game in games:
        for move in game.moves:
            if move.quality not in {"mistake", "blunder"}:
                continue
            all_errors += 1
            if move.fullmove_number >= 30:
                late_errors.append(
                    _example_from_move(
                        move,
                        note="Error after move 30 (possible fatigue / time pressure).",
                    )
                )
    if all_errors > 0 and len(late_errors) / all_errors >= 0.35 and len(late_errors) >= 3:
        rate = len(late_errors) / all_errors
        findings.append(
            HabitFinding(
                id="late_game_errors",
                title="Errors pile up late in games",
                severity=_severity_from_rate(rate, high=0.5, medium=0.35),
                evidence_count=len(late_errors),
                games_affected=len({e.game_id for e in late_errors}),
                rate=round(rate, 4),
                summary=(
                    f"{len(late_errors)}/{all_errors} mistakes/blunders "
                    f"({rate * 100:.0f}%) happened from move 30 onward."
                ),
                practice_hint=(
                    "Practice playing on the clock: leave 1–2 minutes for the late middlegame, "
                    "and use a short checklist (checks, captures, threats) before each move."
                ),
                examples=_top_examples(late_errors),
                thin_evidence=len(late_errors) < 4,
            )
        )

    # --- Mate motifs ---
    missed_mates: list[HabitExample] = []
    allowed_mates: list[HabitExample] = []
    for game in games:
        for move in game.moves:
            if move.quality not in {"mistake", "blunder", "inaccuracy"}:
                continue
            # Missed a mate (or huge forced win) indicated by mate eval before with better move
            if (
                move.mate_before is not None
                and move.mate_before > 0
                and move.preferred_uci
                and move.preferred_uci != move.played_uci
                and move.eval_loss_cp >= settings.mistake_threshold
            ):
                missed_mates.append(
                    _example_from_move(move, note="Missed a forced mate / mating sequence.")
                )
            if (
                move.mate_after is not None
                and move.mate_after < 0
                and (move.mate_before is None or move.mate_before >= 0)
                and move.eval_loss_cp >= settings.mistake_threshold
            ):
                allowed_mates.append(
                    _example_from_move(move, note="Allowed a mating attack after this move.")
                )
            # Also catch critical reason introduced mate
        for cp in game.critical_positions:
            if CriticalReason.INTRODUCED_MATE in cp.reasons:
                allowed_mates.append(
                    _example_from_critical(
                        cp,
                        note="Critical: introduced or allowed forced mate.",
                    )
                )

    if len(missed_mates) >= 2:
        findings.append(
            HabitFinding(
                id="missed_mates",
                title="Missing forced mates",
                severity=HabitSeverity.HIGH if len(missed_mates) >= 3 else HabitSeverity.MEDIUM,
                evidence_count=len(missed_mates),
                games_affected=len({e.game_id for e in missed_mates}),
                rate=None,
                summary=f"Missed mating opportunities in {len(missed_mates)} error moves.",
                practice_hint=(
                    "Drill mate patterns (ladder, back-rank, smothered, Anastasia) and "
                    "always scan checks before other candidate moves."
                ),
                examples=_top_examples(missed_mates),
                thin_evidence=len(missed_mates) < 3,
            )
        )
    if len(allowed_mates) >= 2:
        # Dedupe by game_id+ply
        uniq: dict[tuple[str, int], HabitExample] = {}
        for ex in allowed_mates:
            uniq[(ex.game_id, ex.ply)] = ex
        allowed_list = list(uniq.values())
        findings.append(
            HabitFinding(
                id="king_safety_mates",
                title="Allowing mating attacks",
                severity=HabitSeverity.HIGH if len(allowed_list) >= 3 else HabitSeverity.MEDIUM,
                evidence_count=len(allowed_list),
                games_affected=len({e.game_id for e in allowed_list}),
                rate=None,
                summary=(
                    f"Allowed forced mate or mating attacks in {len(allowed_list)} positions."
                ),
                practice_hint=(
                    "Before committing, ask: can my king be checked? "
                    "Keep back-rank covered and avoid weakening squares around the king."
                ),
                examples=_top_examples(allowed_list),
                thin_evidence=len(allowed_list) < 3,
            )
        )

    # --- High-loss openings (reuse pattern aggregate) ---
    for opening in patterns.high_loss_openings[:2]:
        games_n = int(opening.get("games") or 0)
        acpl = float(opening.get("average_centipawn_loss") or 0.0)
        name = str(opening.get("opening") or "Unknown")
        thin = bool(opening.get("small_sample"))
        if games_n < 2:
            continue
        examples = []
        for game in games:
            key = game.metadata.opening or game.metadata.eco or "Unknown"
            if key != name:
                continue
            if not game.moves:
                continue
            worst = max(game.moves, key=lambda m: m.eval_loss_cp)
            if worst.eval_loss_cp >= settings.inaccuracy_threshold:
                examples.append(
                    _example_from_move(
                        worst,
                        note=f"High-loss move in opening line: {name}.",
                    )
                )
        findings.append(
            HabitFinding(
                id=f"opening::{name[:40]}",
                title=f"High evaluation loss in {name}",
                severity=HabitSeverity.MEDIUM if not thin else HabitSeverity.LOW,
                evidence_count=games_n,
                games_affected=games_n,
                rate=None,
                summary=(
                    f"ACPL {acpl} across {games_n} games in this opening "
                    f"(baseline ACPL "
                    f"{opening.get('baseline_acpl', overall.average_centipawn_loss)})."
                ),
                practice_hint=(
                    "Pick a narrow repertoire response for this line and review the first "
                    "10–12 moves until the plans feel automatic."
                ),
                examples=_top_examples(examples),
                thin_evidence=thin or games_n < 3,
            )
        )

    # --- Color imbalance ---
    by_color = overall.results_by_color
    white = by_color.get("white")
    black = by_color.get("black")
    if (
        white
        and black
        and white.games >= 3
        and black.games >= 3
        and (
            white.win_rate + 0.25 <= black.win_rate
            or black.win_rate + 0.25 <= white.win_rate
        )
    ):
        weak = "white" if white.win_rate < black.win_rate else "black"
        weak_rec = white if weak == "white" else black
        strong_rec = black if weak == "white" else white
        findings.append(
            HabitFinding(
                id=f"color_weakness_{weak}",
                title=f"Weaker results with {weak}",
                severity=HabitSeverity.MEDIUM,
                evidence_count=weak_rec.games,
                games_affected=weak_rec.games,
                rate=round(weak_rec.win_rate, 4),
                summary=(
                    f"Win rate with {weak}: {weak_rec.win_rate * 100:.0f}% "
                    f"({weak_rec.wins}-{weak_rec.losses}-{weak_rec.draws}) vs "
                    f"{'black' if weak == 'white' else 'white'}: "
                    f"{strong_rec.win_rate * 100:.0f}%."
                ),
                practice_hint=(
                    f"Build a simple, solid repertoire as {weak} and review your losses "
                    "in that color for recurring early mistakes."
                ),
                examples=[],
                thin_evidence=weak_rec.games < 5,
            )
        )

    # Strengths (factual)
    if patterns.games_reached_winning >= 3 and patterns.winning_later_drawn_or_lost == 0:
        strengths.append(
            f"Converted or at least did not spoil {patterns.games_reached_winning} "
            "clearly winning positions in this sample."
        )
    if overall.blunders_per_game <= 0.5 and n >= 5:
        strengths.append(
            f"Low blunder rate ({overall.blunders_per_game}/game) across {n} games."
        )
    endgame = next((p for p in overall.by_phase if p.phase == "endgame"), None)
    opening_phase = next((p for p in overall.by_phase if p.phase == "opening"), None)
    if (
        endgame is not None
        and opening_phase is not None
        and endgame.move_count >= 10
        and endgame.average_eval_loss + 15 < opening_phase.average_eval_loss
    ):
        strengths.append(
            "Endgame evaluation loss is lower than opening loss — endgame technique looks "
            "relatively stronger in this sample."
        )

    # Sort findings: high first, then by evidence
    severity_rank = {HabitSeverity.HIGH: 0, HabitSeverity.MEDIUM: 1, HabitSeverity.LOW: 2}
    findings.sort(key=lambda f: (severity_rank[f.severity], -f.evidence_count, f.id))

    # Cap to keep coaching payloads focused
    findings = findings[:6]

    if not findings:
        notes.append("No strong recurring habits detected in this sample.")

    return HabitReport(
        games_analyzed=n,
        findings=findings,
        strengths=strengths,
        notes=notes,
    )


def _phase_practice_hint(phase: str) -> str:
    if phase == "opening":
        return (
            "Slow down in the first 10 moves: develop, castle, and fight for the center "
            "before launching early attacks."
        )
    if phase == "endgame":
        return (
            "Practice basic king-and-pawn and rook endgames; when trading into an ending, "
            "activate your king and create a passed pawn plan."
        )
    return (
        "In middlegames, calculate forcing lines first and ask which pieces are hanging "
        "before and after your move."
    )


def habit_brief_for_coaching(habits: HabitReport) -> dict[str, object]:
    """Compact JSON-friendly habit brief for LLM coaching."""
    return {
        "games_analyzed": habits.games_analyzed,
        "findings": [
            {
                "id": f.id,
                "title": f.title,
                "severity": f.severity.value,
                "evidence_count": f.evidence_count,
                "games_affected": f.games_affected,
                "rate": f.rate,
                "summary": f.summary,
                "practice_hint": f.practice_hint,
                "thin_evidence": f.thin_evidence,
                "examples": [
                    {
                        "game_id": e.game_id,
                        "ply": e.ply,
                        "move": e.fullmove_number,
                        "played": e.played_san,
                        "preferred": e.preferred_san,
                        "loss_cp": e.eval_loss_cp,
                        "phase": e.phase,
                        "fen": e.fen,
                        "note": e.note,
                    }
                    for e in f.examples
                ],
            }
            for f in habits.findings
        ],
        "strengths": habits.strengths,
        "notes": habits.notes,
    }
