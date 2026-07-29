"""OpenAI coaching grounded on Stockfish analysis (Stage 2)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from check_yourself.analysis.habit_analyzer import habit_brief_for_coaching
from check_yourself.analysis.tactics_analyzer import tactics_brief_for_coaching
from check_yourself.coaching.profile_store import profile_brief_for_coaching
from check_yourself.config import AnalysisSettings
from check_yourself.models import (
    AnalysisReport,
    CoachingReport,
    CriticalCoachingNote,
    GameAnalysisResult,
    GameCoaching,
    PlayerCoachingProfile,
)

logger = logging.getLogger(__name__)

INSTRUCTION_PACK = "v1"

SYSTEM_PROMPT = """You are a practical chess coach for Check Yourself.
You receive Stockfish-derived facts, a deterministic habit brief, and optionally
a durable prior coaching profile for this same player. Treat engine facts as ground truth.

Rules:
- Do not invent tactics, evaluations, moves, or habits that contradict the provided facts.
- Prioritize the habit brief: explain the top weaknesses with concrete practice advice.
- When prior_profile is present, explicitly note what is continuing, what improved,
  and what is new versus previous sessions. Reuse prior themes when still valid.
- Tie advice to example plies/FENs when present; do not invent new positions.
- Prefer concrete, actionable feedback; avoid generic platitudes.
- If a habit is marked thin_evidence, say the sample is small and hedge accordingly.
- Explain ideas in plain language a club player can use in the next game.
"""


class CoachingError(Exception):
    """OpenAI coaching failure (safe for display; never includes API keys)."""


class CoachingProvider(Protocol):
    def coach(
        self,
        report: AnalysisReport,
        *,
        prior_profile: PlayerCoachingProfile | None = None,
    ) -> CoachingReport: ...


def build_game_coaching_payload(
    game: GameAnalysisResult,
    *,
    max_critical: int = 5,
    max_error_moves: int = 8,
) -> dict[str, Any]:
    """Compact engine-grounded payload for one game (keeps token cost low)."""
    meta = game.metadata
    critical = []
    for cp in game.critical_positions[:max_critical]:
        critical.append(
            {
                "ply": cp.ply,
                "move": cp.fullmove_number,
                "played": cp.played_san,
                "preferred": cp.preferred_san,
                "loss_cp": cp.eval_loss_cp,
                "quality": cp.quality,
                "phase": cp.game_phase,
                "reasons": [r.value for r in cp.reasons],
                "engine_note": cp.explanation,
                "fen": cp.fen,
                "pv": cp.principal_variation,
            }
        )

    errors = [
        m
        for m in game.moves
        if m.quality in {"inaccuracy", "mistake", "blunder"}
    ]
    errors.sort(key=lambda m: m.eval_loss_cp, reverse=True)
    error_moves = [
        {
            "ply": m.ply,
            "move": m.fullmove_number,
            "played": m.played_san,
            "preferred": m.preferred_san,
            "loss_cp": m.eval_loss_cp,
            "quality": m.quality,
            "phase": m.game_phase,
            "fen": m.fen_before,
        }
        for m in errors[:max_error_moves]
    ]

    return {
        "game_id": meta.game_id,
        "color": meta.user_color,
        "result": meta.result,
        "opening": meta.opening,
        "eco": meta.eco,
        "time_class": meta.time_class,
        "pgn": meta.pgn,
        "acpl": game.average_centipawn_loss,
        "inaccuracies": game.inaccuracy_count,
        "mistakes": game.mistake_count,
        "blunders": game.blunder_count,
        "critical_positions": critical,
        "top_error_moves": error_moves,
    }


def build_report_coaching_payload(
    report: AnalysisReport,
    games: list[GameAnalysisResult],
    *,
    max_critical: int = 5,
    max_error_moves: int = 8,
    prior_profile: PlayerCoachingProfile | None = None,
) -> dict[str, Any]:
    overall = report.overall
    payload: dict[str, Any] = {
        "player": report.settings.username,
        "games_analyzed": overall.games_analyzed,
        "record": {
            "wins": overall.wins,
            "losses": overall.losses,
            "draws": overall.draws,
            "win_rate": overall.win_rate,
        },
        "average_centipawn_loss": overall.average_centipawn_loss,
        "inaccuracies_per_game": overall.inaccuracies_per_game,
        "mistakes_per_game": overall.mistakes_per_game,
        "blunders_per_game": overall.blunders_per_game,
        "patterns": overall.patterns.model_dump(),
        "by_phase": [p.model_dump() for p in overall.by_phase],
        "games": [
            build_game_coaching_payload(
                g,
                max_critical=max_critical,
                max_error_moves=max_error_moves,
            )
            for g in games
        ],
    }
    if report.habits is not None:
        payload["habit_brief"] = habit_brief_for_coaching(report.habits)
    if report.tactics is not None:
        payload["tactics_brief"] = tactics_brief_for_coaching(report.tactics)
    if prior_profile is not None and prior_profile.sessions:
        payload["prior_profile"] = profile_brief_for_coaching(prior_profile)
    return payload


_COACHING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "overall_summary": {"type": "string"},
        "themes": {"type": "array", "items": {"type": "string"}},
        "practice_suggestions": {"type": "array", "items": {"type": "string"}},
        "games": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "game_id": {"type": "string"},
                    "summary": {"type": "string"},
                    "themes": {"type": "array", "items": {"type": "string"}},
                    "critical_notes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "ply": {"type": "integer"},
                                "note": {"type": "string"},
                            },
                            "required": ["ply", "note"],
                        },
                    },
                    "practice_suggestions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "game_id",
                    "summary",
                    "themes",
                    "critical_notes",
                    "practice_suggestions",
                ],
            },
        },
    },
    "required": ["overall_summary", "themes", "practice_suggestions", "games"],
}


def _parse_coaching_content(content: str, *, model: str) -> CoachingReport:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise CoachingError(f"OpenAI returned invalid JSON: {exc}") from exc

    games: list[GameCoaching] = []
    for item in data.get("games") or []:
        notes = [
            CriticalCoachingNote(ply=int(n["ply"]), note=str(n["note"]))
            for n in (item.get("critical_notes") or [])
            if "ply" in n and "note" in n
        ]
        games.append(
            GameCoaching(
                game_id=str(item["game_id"]),
                summary=str(item.get("summary") or ""),
                themes=[str(t) for t in (item.get("themes") or [])],
                critical_notes=notes,
                practice_suggestions=[
                    str(s) for s in (item.get("practice_suggestions") or [])
                ],
            )
        )

    return CoachingReport(
        model=model,
        instruction_pack=INSTRUCTION_PACK,
        overall_summary=str(data.get("overall_summary") or ""),
        themes=[str(t) for t in (data.get("themes") or [])],
        practice_suggestions=[str(s) for s in (data.get("practice_suggestions") or [])],
        games=games,
        generated_at=datetime.now(UTC),
    )


def _merge_coaching_chunks(chunks: list[CoachingReport], *, model: str) -> CoachingReport:
    if not chunks:
        raise CoachingError("No coaching chunks to merge")
    if len(chunks) == 1:
        return chunks[0]

    games: list[GameCoaching] = []
    themes: list[str] = []
    practice: list[str] = []
    summaries: list[str] = []
    seen_themes: set[str] = set()
    seen_practice: set[str] = set()
    for chunk in chunks:
        games.extend(chunk.games)
        summaries.append(chunk.overall_summary)
        for theme in chunk.themes:
            if theme not in seen_themes:
                seen_themes.add(theme)
                themes.append(theme)
        for tip in chunk.practice_suggestions:
            if tip not in seen_practice:
                seen_practice.add(tip)
                practice.append(tip)

    overall = " ".join(s.strip() for s in summaries if s.strip())
    return CoachingReport(
        model=model,
        instruction_pack=INSTRUCTION_PACK,
        overall_summary=overall,
        themes=themes[:8],
        practice_suggestions=practice[:8],
        games=games,
        generated_at=datetime.now(UTC),
    )


class OpenAICoachingProvider:
    """Chat Completions coaching via httpx (no OpenAI SDK required)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4.1-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
        max_critical: int = 5,
        max_error_moves: int = 8,
        chunk_size: int = 5,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise CoachingError("OpenAI API key is empty")
        self._api_key = api_key.strip()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_critical = max_critical
        self.max_error_moves = max_error_moves
        self.chunk_size = max(1, chunk_size)
        self._client = httpx.Client(
            base_url=self.base_url + "/",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_settings(
        cls,
        settings: AnalysisSettings,
        *,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> OpenAICoachingProvider:
        key = api_key or settings.resolve_openai_api_key()
        if not key:
            raise CoachingError(
                "OpenAI API key not found. Set OPENAI_API_KEY or "
                "CHECK_YOURSELF_OPENAI_API_KEY, or pass --openai-api-key."
            )
        return cls(
            key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout,
            max_critical=settings.coach_max_critical,
            max_error_moves=settings.coach_max_error_moves,
            chunk_size=settings.coach_chunk_size,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenAICoachingProvider:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def coach(
        self,
        report: AnalysisReport,
        *,
        prior_profile: PlayerCoachingProfile | None = None,
    ) -> CoachingReport:
        if not report.games:
            return CoachingReport(
                model=self.model,
                instruction_pack=INSTRUCTION_PACK,
                overall_summary="No games were available to coach.",
                themes=[],
                practice_suggestions=[],
                games=[],
                generated_at=datetime.now(UTC),
            )

        chunks: list[CoachingReport] = []
        for start in range(0, len(report.games), self.chunk_size):
            batch = report.games[start : start + self.chunk_size]
            # Only attach prior profile on the first chunk to control tokens.
            prior = prior_profile if start == 0 else None
            chunks.append(self._coach_games(report, batch, prior_profile=prior))
        return _merge_coaching_chunks(chunks, model=self.model)

    def _coach_games(
        self,
        report: AnalysisReport,
        games: list[GameAnalysisResult],
        *,
        prior_profile: PlayerCoachingProfile | None = None,
    ) -> CoachingReport:
        payload = build_report_coaching_payload(
            report,
            games,
            max_critical=self.max_critical,
            max_error_moves=self.max_error_moves,
            prior_profile=prior_profile,
        )
        memory_note = (
            " Use prior_profile to compare against earlier sessions."
            if prior_profile is not None and prior_profile.sessions
            else ""
        )
        user_prompt = (
            "Produce coaching for this Stockfish-backed analysis payload. "
            "Lead with the habit_brief (cross-game weaknesses) when present, "
            "use tactics_brief (mating pieces, blunder pieces, forks/pins/skewers/"
            "discovered attacks) when present, "
            f"then cover each listed game_id.{memory_note} "
            "Return JSON matching the schema.\n\n"
            f"{json.dumps(payload, separators=(',', ':'))}"
        )
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "coaching_report",
                    "strict": True,
                    "schema": _COACHING_SCHEMA,
                },
            },
        }
        try:
            response = self._client.post("chat/completions", json=body)
        except httpx.HTTPError as exc:
            raise CoachingError(f"Could not reach OpenAI: {exc}") from exc

        if response.status_code == 401:
            raise CoachingError("OpenAI authentication failed (check your API key)")
        if response.status_code == 429:
            raise CoachingError("OpenAI rate limited the coaching request")
        if response.status_code >= 400:
            # Never echo response bodies that might contain sensitive request echoes.
            raise CoachingError(f"OpenAI HTTP {response.status_code} during coaching")

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise CoachingError("OpenAI response missing coaching content") from exc
        if not isinstance(content, str) or not content.strip():
            raise CoachingError("OpenAI returned empty coaching content")
        return _parse_coaching_content(content, model=self.model)


def probe_openai_key(api_key: str | None) -> tuple[bool, str]:
    """Check whether an API key appears configured (does not call OpenAI)."""
    if api_key and api_key.strip():
        return True, "API key configured (not validated against OpenAI)"
    return False, "No OPENAI_API_KEY / CHECK_YOURSELF_OPENAI_API_KEY set"
