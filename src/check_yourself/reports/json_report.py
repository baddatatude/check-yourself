"""JSON report writer."""

from __future__ import annotations

import json
from pathlib import Path

from check_yourself.models import AnalysisReport, GameAnalysisResult


def write_analysis_json(report: AnalysisReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return path


def write_game_json(game: GameAnalysisResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(game.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_analysis_json(path: Path) -> AnalysisReport:
    data = json.loads(path.read_text(encoding="utf-8"))
    return AnalysisReport.model_validate(data)
