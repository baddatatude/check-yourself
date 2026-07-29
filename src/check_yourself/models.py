"""Pydantic domain models for Check Yourself analysis."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.4.0"
PLAYER_PROFILE_SCHEMA_VERSION = "1.0.0"

PlayerColor = Literal["white", "black"]
GamePhase = Literal["opening", "middlegame", "endgame"]
MoveQuality = Literal[
    "best",
    "excellent",
    "good",
    "inaccuracy",
    "mistake",
    "blunder",
]
TimeClass = Literal["bullet", "blitz", "rapid", "daily", "classical", "unknown"]


class EvalKind(StrEnum):
    CP = "cp"
    MATE = "mate"


class Evaluation(BaseModel):
    """Normalized evaluation from a player's perspective."""

    kind: EvalKind
    value: int = Field(description="Centipawns or mate distance (positive = good for player)")
    white_cp: int | None = None
    white_mate: int | None = None

    def display(self) -> str:
        if self.kind == EvalKind.MATE:
            sign = "+" if self.value > 0 else "-"
            return f"{sign}M{abs(self.value)}"
        return f"{self.value / 100:+.2f}"


class GameMetadata(BaseModel):
    """Raw game metadata from Chess.com / PGN headers."""

    game_id: str
    url: str | None = None
    end_time: int | None = None
    white: str
    black: str
    result: str
    user_color: PlayerColor
    time_control: str | None = None
    time_class: TimeClass = "unknown"
    rated: bool | None = None
    opening: str | None = None
    eco: str | None = None
    event: str | None = None
    site: str | None = None
    date: str | None = None
    white_elo: str | None = None
    black_elo: str | None = None
    termination: str | None = None
    pgn: str


class MoveAnalysis(BaseModel):
    """Per-move Stockfish analysis for the requested player's move."""

    game_id: str
    player_color: PlayerColor
    ply: int
    fullmove_number: int
    fen_before: str
    played_san: str
    played_uci: str
    preferred_uci: str | None = None
    preferred_san: str | None = None
    principal_variation: list[str] = Field(default_factory=list)
    eval_before: Evaluation
    eval_after: Evaluation
    eval_loss_cp: int
    mate_before: int | None = None
    mate_after: int | None = None
    quality: MoveQuality
    game_phase: GamePhase
    result: str
    time_control: str | None = None
    time_class: TimeClass = "unknown"
    opening: str | None = None
    eco: str | None = None
    clock: str | None = None


class CriticalReason(StrEnum):
    LARGEST_EVAL_LOSS = "largest_eval_loss"
    WINNING_TO_EQUAL = "winning_to_equal"
    WINNING_OR_EQUAL_TO_LOSING = "winning_or_equal_to_losing"
    MISSED_WIN = "missed_winning_opportunity"
    MISSED_DEFENSE = "missed_defensive_resource"
    INTRODUCED_MATE = "introduced_or_allowed_forced_mate"
    TURNING_POINT = "major_turning_point"


class CriticalPosition(BaseModel):
    game_id: str
    ply: int
    fullmove_number: int
    fen: str
    player_color: PlayerColor
    played_san: str
    played_uci: str
    preferred_san: str | None = None
    preferred_uci: str | None = None
    principal_variation: list[str] = Field(default_factory=list)
    eval_before: Evaluation
    eval_after: Evaluation
    eval_loss_cp: int
    quality: MoveQuality
    game_phase: GamePhase
    reasons: list[CriticalReason]
    importance_score: float
    explanation: str


class PhaseStats(BaseModel):
    phase: GamePhase
    move_count: int = 0
    average_eval_loss: float = 0.0
    total_eval_loss: float = 0.0
    mistake_count: int = 0
    blunder_count: int = 0
    share_of_total_eval_loss: float = 0.0


class OpeningStats(BaseModel):
    opening: str
    eco: str | None = None
    games_played: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    average_centipawn_loss: float = 0.0
    mistakes_per_game: float = 0.0
    blunders_per_game: float = 0.0
    small_sample: bool = True


class ColorRecord(BaseModel):
    wins: int = 0
    losses: int = 0
    draws: int = 0

    @property
    def games(self) -> int:
        return self.wins + self.losses + self.draws

    @property
    def win_rate(self) -> float:
        return (self.wins / self.games) if self.games else 0.0


class PatternIndicators(BaseModel):
    games_reached_winning: int = 0
    winning_later_drawn_or_lost: int = 0
    equal_later_lost: int = 0
    largest_loss_move_ranges: list[dict[str, Any]] = Field(default_factory=list)
    largest_loss_phases: list[dict[str, Any]] = Field(default_factory=list)
    high_loss_openings: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class OverallStats(BaseModel):
    games_analyzed: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    win_rate: float = 0.0
    results_by_color: dict[str, ColorRecord] = Field(default_factory=dict)
    results_by_time_control: dict[str, ColorRecord] = Field(default_factory=dict)
    average_game_length: float = 0.0
    average_centipawn_loss: float = 0.0
    median_centipawn_loss: float = 0.0
    inaccuracies_per_game: float = 0.0
    mistakes_per_game: float = 0.0
    blunders_per_game: float = 0.0
    total_critical_positions: int = 0
    by_phase: list[PhaseStats] = Field(default_factory=list)
    by_opening: list[OpeningStats] = Field(default_factory=list)
    patterns: PatternIndicators = Field(default_factory=PatternIndicators)


class GameAnalysisResult(BaseModel):
    metadata: GameMetadata
    moves: list[MoveAnalysis]
    critical_positions: list[CriticalPosition]
    average_centipawn_loss: float = 0.0
    inaccuracy_count: int = 0
    mistake_count: int = 0
    blunder_count: int = 0
    eval_graph: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Player-POV eval after each of the player's moves",
    )


class AnalysisRunSettings(BaseModel):
    username: str
    games_requested: int
    games_found: int
    platform: str = "chess.com"
    time_control_filter: str | None = None
    stockfish_path: str
    depth: int
    multipv: int
    pv_moves: int
    inaccuracy_threshold: int
    mistake_threshold: int
    blunder_threshold: int
    max_critical_positions: int
    analyzed_at: datetime
    coaching_enabled: bool = False
    coaching_model: str | None = None


class CriticalCoachingNote(BaseModel):
    ply: int
    note: str


class GameCoaching(BaseModel):
    game_id: str
    summary: str
    themes: list[str] = Field(default_factory=list)
    critical_notes: list[CriticalCoachingNote] = Field(default_factory=list)
    practice_suggestions: list[str] = Field(default_factory=list)


class CoachingReport(BaseModel):
    """LLM coaching grounded on Stockfish critical positions (optional Stage 2)."""

    model: str
    instruction_pack: str = "v1"
    overall_summary: str
    themes: list[str] = Field(default_factory=list)
    practice_suggestions: list[str] = Field(default_factory=list)
    games: list[GameCoaching] = Field(default_factory=list)
    generated_at: datetime


class HabitSeverity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class HabitExample(BaseModel):
    game_id: str
    ply: int
    fullmove_number: int
    fen: str
    played_san: str
    preferred_san: str | None = None
    played_uci: str | None = None
    preferred_uci: str | None = None
    eval_loss_cp: int
    quality: MoveQuality
    phase: GamePhase
    note: str
    player_color: PlayerColor | None = None


class HabitFinding(BaseModel):
    """One deterministic cross-game weakness / habit."""

    id: str
    title: str
    severity: HabitSeverity
    evidence_count: int = 0
    games_affected: int = 0
    rate: float | None = Field(
        default=None,
        description="Share of relevant games or errors supporting this habit (0–1)",
    )
    summary: str
    practice_hint: str
    examples: list[HabitExample] = Field(default_factory=list)
    thin_evidence: bool = False


class HabitReport(BaseModel):
    """Engine-derived habit brief used for coaching and HTML."""

    games_analyzed: int = 0
    findings: list[HabitFinding] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TacticKind(StrEnum):
    FORK = "fork"
    PIN = "pin"
    SKEWER = "skewer"
    DISCOVERED_ATTACK = "discovered_attack"


class PieceCount(BaseModel):
    piece: str
    count: int = 0
    share: float = 0.0
    total_eval_loss_cp: int = 0


class TacticExample(BaseModel):
    kind: TacticKind
    game_id: str
    ply: int
    fullmove_number: int
    fen: str
    fen_after_error: str | None = None
    played_san: str
    played_uci: str | None = None
    preferred_san: str | None = None
    preferred_uci: str | None = None
    opponent_reply_san: str | None = None
    opponent_reply_uci: str | None = None
    eval_loss_cp: int
    quality: MoveQuality
    phase: GamePhase
    player_color: PlayerColor
    note: str


class TacticCount(BaseModel):
    kind: TacticKind
    count: int = 0
    share: float = Field(
        default=0.0,
        description="Share of scanned mistakes/blunders where this motif appeared",
    )
    examples: list[TacticExample] = Field(default_factory=list)


class TacticsReport(BaseModel):
    """Piece-level and tactical-motif breakdown from engine-tagged errors + PGNs."""

    games_analyzed: int = 0
    games_checkmated: int = 0
    errors_scanned: int = 0
    mated_by_piece: list[PieceCount] = Field(default_factory=list)
    blunders_by_piece: list[PieceCount] = Field(default_factory=list)
    tactics_that_hurt: list[TacticCount] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    schema_version: str = SCHEMA_VERSION
    settings: AnalysisRunSettings
    overall: OverallStats
    games: list[GameAnalysisResult]
    warnings: list[str] = Field(default_factory=list)
    habits: HabitReport | None = None
    tactics: TacticsReport | None = None
    coaching: CoachingReport | None = None


class ProfileSessionRef(BaseModel):
    report_path: str
    analyzed_at: datetime
    games_analyzed: int
    platform: str
    coaching_model: str | None = None


class PersistentHabitNote(BaseModel):
    id: str
    title: str
    severity: str
    summary: str
    practice_hint: str
    first_seen_at: datetime
    last_seen_at: datetime
    times_seen: int = 1
    status: Literal["active", "improved", "resolved"] = "active"


class PlayerCoachingProfile(BaseModel):
    """Durable per-player coaching memory across analysis sessions."""

    schema_version: str = PLAYER_PROFILE_SCHEMA_VERSION
    username: str
    platform: str = "chess.com"
    created_at: datetime
    updated_at: datetime
    sessions: list[ProfileSessionRef] = Field(default_factory=list)
    active_habits: list[PersistentHabitNote] = Field(default_factory=list)
    recurring_themes: list[str] = Field(default_factory=list)
    practice_focus: list[str] = Field(default_factory=list)
    coach_narrative: str = ""
    recent_session_summaries: list[str] = Field(default_factory=list)
