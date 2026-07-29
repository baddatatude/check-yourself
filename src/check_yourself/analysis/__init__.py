"""Analysis package."""

from check_yourself.analysis.aggregate import aggregate_stats
from check_yourself.analysis.critical_positions import select_critical_positions
from check_yourself.analysis.game_analyzer import GameAnalyzer, result_for_player
from check_yourself.analysis.game_phase import classify_game_phase
from check_yourself.analysis.habit_analyzer import analyze_habits, habit_brief_for_coaching

__all__ = [
    "GameAnalyzer",
    "aggregate_stats",
    "analyze_habits",
    "classify_game_phase",
    "habit_brief_for_coaching",
    "result_for_player",
    "select_critical_positions",
]
