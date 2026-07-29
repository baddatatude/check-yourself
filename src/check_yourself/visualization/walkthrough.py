"""Board walkthrough sequences and square heatmaps for HTML reports."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from check_yourself.models import (
    AnalysisReport,
    CriticalPosition,
    GameAnalysisResult,
    HabitExample,
    MoveAnalysis,
)

FILES = "abcdefgh"
RANKS = "12345678"


def _uci_squares(uci: str | None) -> tuple[str | None, str | None]:
    if not uci or len(uci) < 4:
        return None, None
    fr, to = uci[:2].lower(), uci[2:4].lower()
    if fr[0] not in FILES or fr[1] not in RANKS:
        return None, None
    if to[0] not in FILES or to[1] not in RANKS:
        return None, None
    return fr, to


def _index_moves(games: list[GameAnalysisResult]) -> dict[tuple[str, int], MoveAnalysis]:
    out: dict[tuple[str, int], MoveAnalysis] = {}
    for game in games:
        for move in game.moves:
            out[(move.game_id, move.ply)] = move
    return out


def _index_criticals(games: list[GameAnalysisResult]) -> dict[tuple[str, int], CriticalPosition]:
    out: dict[tuple[str, int], CriticalPosition] = {}
    for game in games:
        for cp in game.critical_positions:
            out[(cp.game_id, cp.ply)] = cp
    return out


def _resolve_step(
    *,
    fen: str,
    game_id: str,
    ply: int,
    fullmove_number: int,
    played_san: str,
    preferred_san: str | None,
    played_uci: str | None,
    preferred_uci: str | None,
    eval_loss_cp: int,
    quality: str,
    phase: str,
    caption: str,
    player_color: str | None,
    coach_note: str | None = None,
    move_index: dict[tuple[str, int], MoveAnalysis],
) -> dict[str, Any]:
    move = move_index.get((game_id, ply))
    orientation = player_color or (move.player_color if move else "white")
    return {
        "fen": fen,
        "orientation": orientation,
        "game_id": game_id,
        "ply": ply,
        "fullmove_number": fullmove_number,
        "played_san": played_san,
        "preferred_san": preferred_san or (move.preferred_san if move else None),
        "played_uci": played_uci or (move.played_uci if move else None),
        "preferred_uci": preferred_uci or (move.preferred_uci if move else None),
        "eval_loss_cp": eval_loss_cp,
        "quality": quality,
        "phase": phase,
        "caption": caption,
        "coach_note": coach_note,
    }


def _step_from_example(
    ex: HabitExample,
    move_index: dict[tuple[str, int], MoveAnalysis],
    *,
    coach_note: str | None = None,
) -> dict[str, Any]:
    return _resolve_step(
        fen=ex.fen,
        game_id=ex.game_id,
        ply=ex.ply,
        fullmove_number=ex.fullmove_number,
        played_san=ex.played_san,
        preferred_san=ex.preferred_san,
        played_uci=ex.played_uci,
        preferred_uci=ex.preferred_uci,
        eval_loss_cp=ex.eval_loss_cp,
        quality=ex.quality,
        phase=ex.phase,
        caption=ex.note,
        player_color=ex.player_color,
        coach_note=coach_note,
        move_index=move_index,
    )


def _step_from_critical(
    cp: CriticalPosition,
    move_index: dict[tuple[str, int], MoveAnalysis],
    *,
    coach_note: str | None = None,
) -> dict[str, Any]:
    return _resolve_step(
        fen=cp.fen,
        game_id=cp.game_id,
        ply=cp.ply,
        fullmove_number=cp.fullmove_number,
        played_san=cp.played_san,
        preferred_san=cp.preferred_san,
        played_uci=cp.played_uci,
        preferred_uci=cp.preferred_uci,
        eval_loss_cp=cp.eval_loss_cp,
        quality=cp.quality,
        phase=cp.game_phase,
        caption=cp.explanation,
        player_color=cp.player_color,
        coach_note=coach_note,
        move_index=move_index,
    )


def _bump(heatmap: dict[str, float], square: str | None, weight: float = 1.0) -> None:
    if square:
        heatmap[square] = round(heatmap.get(square, 0.0) + weight, 2)


def build_heatmaps(report: AnalysisReport) -> dict[str, dict[str, float]]:
    """Aggregate from/to squares for errors and critical mistakes."""
    blunder_to: dict[str, float] = {}
    blunder_from: dict[str, float] = {}
    mistake_to: dict[str, float] = {}
    critical_to: dict[str, float] = {}
    loss_to: dict[str, float] = {}

    for game in report.games:
        for move in game.moves:
            fr, to = _uci_squares(move.played_uci)
            # Cap mate-skewed losses so heatmaps stay readable
            weight = min(float(move.eval_loss_cp), 800.0) / 100.0
            if move.quality == "blunder":
                _bump(blunder_to, to, 1.0)
                _bump(blunder_from, fr, 1.0)
                _bump(loss_to, to, weight)
            elif move.quality == "mistake":
                _bump(mistake_to, to, 1.0)
                _bump(loss_to, to, weight * 0.6)
            elif move.quality == "inaccuracy":
                _bump(loss_to, to, weight * 0.25)
        for cp in game.critical_positions:
            _, to = _uci_squares(cp.played_uci)
            _bump(critical_to, to, 1.0)

    return {
        "blunder_to": blunder_to,
        "blunder_from": blunder_from,
        "mistake_to": mistake_to,
        "critical_to": critical_to,
        "loss_weighted_to": loss_to,
    }


def build_walkthrough_sequences(report: AnalysisReport) -> list[dict[str, Any]]:
    """Theme / habit sequences for click-through board walkthroughs."""
    move_index = _index_moves(report.games)
    critical_index = _index_criticals(report.games)
    sequences: list[dict[str, Any]] = []

    if report.habits and report.habits.findings:
        for finding in report.habits.findings:
            steps = [
                _step_from_example(ex, move_index) for ex in finding.examples if ex.fen
            ]
            if not steps:
                continue
            sequences.append(
                {
                    "id": f"habit:{finding.id}",
                    "kind": "habit",
                    "title": finding.title,
                    "severity": finding.severity.value,
                    "summary": finding.summary,
                    "practice_hint": finding.practice_hint,
                    "steps": steps,
                }
            )

    # Coaching themes → critical positions from games tagged with that theme
    if report.coaching and report.coaching.themes:
        notes_by_game_ply: dict[tuple[str, int], str] = {}
        game_themes: dict[str, set[str]] = defaultdict(set)
        for gc in report.coaching.games:
            for theme in gc.themes:
                game_themes[gc.game_id].add(theme.lower())
            for note in gc.critical_notes:
                notes_by_game_ply[(gc.game_id, note.ply)] = note.note

        for theme in report.coaching.themes:
            theme_l = theme.lower()
            steps: list[dict[str, Any]] = []
            seen: set[tuple[str, int]] = set()
            for game in report.games:
                themes = game_themes.get(game.metadata.game_id, set())
                # Match if game lists theme, or theme words overlap habit-like tags
                if theme_l not in themes and not any(
                    token in " ".join(themes) for token in theme_l.split() if len(token) > 4
                ):
                    # Still include criticals with coach notes when theme appears in note text
                    for cp in game.critical_positions:
                        note = notes_by_game_ply.get((cp.game_id, cp.ply), "")
                        if theme_l[:18].lower() in note.lower() or any(
                            w in note.lower() for w in theme_l.split() if len(w) > 5
                        ):
                            key = (cp.game_id, cp.ply)
                            if key not in seen:
                                seen.add(key)
                                steps.append(
                                    _step_from_critical(
                                        cp,
                                        move_index,
                                        coach_note=note or None,
                                    )
                                )
                    continue
                for cp in sorted(
                    game.critical_positions,
                    key=lambda c: -c.eval_loss_cp,
                )[:3]:
                    key = (cp.game_id, cp.ply)
                    if key in seen:
                        continue
                    seen.add(key)
                    steps.append(
                        _step_from_critical(
                            cp,
                            move_index,
                            coach_note=notes_by_game_ply.get(key),
                        )
                    )
            # Fallback: top criticals overall if theme matching was thin
            if len(steps) < 2:
                for cp in sorted(
                    critical_index.values(),
                    key=lambda c: -c.eval_loss_cp,
                ):
                    key = (cp.game_id, cp.ply)
                    if key in seen:
                        continue
                    note = notes_by_game_ply.get(key, "")
                    if theme_l.split()[0].lower() in (note + " " + cp.explanation).lower():
                        seen.add(key)
                        steps.append(
                            _step_from_critical(cp, move_index, coach_note=note or None)
                        )
                    if len(steps) >= 5:
                        break
            if steps:
                sequences.append(
                    {
                        "id": f"theme:{theme}",
                        "kind": "theme",
                        "title": theme,
                        "severity": None,
                        "summary": f"Positions linked to the coaching theme “{theme}”.",
                        "practice_hint": None,
                        "steps": steps[:8],
                    }
                )

    # Always include a biggest-swings tour
    top_criticals = sorted(
        (cp for g in report.games for cp in g.critical_positions),
        key=lambda c: -c.eval_loss_cp,
    )[:12]
    if top_criticals:
        notes_by_game_ply = {}
        if report.coaching:
            for gc in report.coaching.games:
                for note in gc.critical_notes:
                    notes_by_game_ply[(gc.game_id, note.ply)] = note.note
        sequences.insert(
            0,
            {
                "id": "critical:biggest_swings",
                "kind": "critical",
                "title": "Biggest evaluation swings",
                "severity": "high",
                "summary": (
                    "Largest Stockfish evaluation drops in this sample — "
                    "click through to see what was played vs preferred."
                ),
                "practice_hint": (
                    "Pause on each board: name a candidate, then compare the green arrow."
                ),
                "steps": [
                    _step_from_critical(
                        cp,
                        move_index,
                        coach_note=notes_by_game_ply.get((cp.game_id, cp.ply)),
                    )
                    for cp in top_criticals
                ],
            },
        )

    if report.tactics is not None:
        for row in report.tactics.tactics_that_hurt:
            steps = []
            for ex in row.examples:
                steps.append(
                    _resolve_step(
                        fen=ex.fen,
                        game_id=ex.game_id,
                        ply=ex.ply,
                        fullmove_number=ex.fullmove_number,
                        played_san=ex.played_san,
                        preferred_san=ex.preferred_san,
                        played_uci=ex.played_uci,
                        preferred_uci=ex.preferred_uci,
                        eval_loss_cp=ex.eval_loss_cp,
                        quality=ex.quality,
                        phase=ex.phase,
                        caption=ex.note,
                        player_color=ex.player_color,
                        coach_note=(
                            f"Opponent reply motif: {ex.opponent_reply_san}"
                            if ex.opponent_reply_san
                            else None
                        ),
                        move_index=move_index,
                    )
                )
            if steps:
                sequences.append(
                    {
                        "id": f"tactic:{row.kind.value}",
                        "kind": "tactic",
                        "title": f"{row.kind.value.replace('_', ' ').title()}s that hurt you",
                        "severity": "high" if row.count >= 5 else "medium",
                        "summary": (
                            f"Found in {row.count} mistake/blunder positions "
                            f"({row.share:.0%} of scanned errors)."
                        ),
                        "practice_hint": (
                            "Before moving, scan for opponent forks, pins, skewers, "
                            "and discovered checks."
                        ),
                        "steps": steps,
                    }
                )

    # Deduplicate sequences with identical titles keeping first
    seen_titles: set[str] = set()
    unique: list[dict[str, Any]] = []
    for seq in sequences:
        title = seq["title"].strip().lower()
        if title in seen_titles:
            continue
        seen_titles.add(title)
        unique.append(seq)
    return unique


def build_board_aids(report: AnalysisReport) -> dict[str, Any]:
    """Payload embedded in the HTML report for interactive boards."""
    return {
        "sequences": build_walkthrough_sequences(report),
        "heatmaps": build_heatmaps(report),
        "heatmap_labels": {
            "blunder_to": "Blunder destinations",
            "blunder_from": "Blunder origins",
            "mistake_to": "Mistake destinations",
            "critical_to": "Critical-move destinations",
            "loss_weighted_to": "Eval-loss weighted destinations",
        },
    }
