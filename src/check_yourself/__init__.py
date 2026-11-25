"""Check Yourself public API for local PGN analysis with Stockfish."""

from __future__ import annotations

__version__ = "0.2.0"
__tagline__ = "Check yourself before your rating wrecks itself."

from check_yourself.api import (
    AnalysisError,
    AnalysisOptions,
    AnalysisProvenance,
    AnalysisResult,
    PGNError,
    StockfishError,
    analyze_game,
    analyze_games,
)
from check_yourself.models import (
    BehaviorSummary,
    Continuation,
    ContinuationMove,
    CriticalPosition,
    Evaluation,
    GameAnalysisResult,
    MoveAnalysis,
    TimelinePosition,
    TrainingExercise,
)

__all__ = [
    "AnalysisError",
    "AnalysisOptions",
    "AnalysisProvenance",
    "AnalysisResult",
    "BehaviorSummary",
    "Continuation",
    "ContinuationMove",
    "CriticalPosition",
    "Evaluation",
    "GameAnalysisResult",
    "MoveAnalysis",
    "PGNError",
    "StockfishError",
    "TimelinePosition",
    "TrainingExercise",
    "analyze_game",
    "analyze_games",
]
