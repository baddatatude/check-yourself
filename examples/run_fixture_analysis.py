#!/usr/bin/env python3
"""Fixture-backed analysis demo (no network, no Stockfish)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from check_yourself.config import AnalysisSettings
from check_yourself.pipeline import analyze_games_offline
from check_yourself.providers.chess_com import parse_pgn_metadata
from tests.fixtures.mock_engine import ScriptedLossEngine
from tests.fixtures.sample_data import SAMPLE_PGN_BLACK, SAMPLE_PGN_RAPID, SAMPLE_PGN_WHITE


def main() -> None:
    out = Path("reports")
    settings = AnalysisSettings(depth=4, max_critical_positions=3)
    engine = ScriptedLossEngine(start_cp=180, drop_per_player_move=120)
    metas = []
    for pgn, end in (
        (SAMPLE_PGN_WHITE, 1_700_000_001),
        (SAMPLE_PGN_BLACK, 1_700_000_002),
        (SAMPLE_PGN_RAPID, 1_700_000_003),
    ):
        meta = parse_pgn_metadata(pgn, username="TestPlayer", end_time=end)
        assert meta is not None
        metas.append(meta)

    report, run_dir = analyze_games_offline(
        "TestPlayer",
        metas,
        engine,
        settings=settings,
        output_dir=out,
        games_requested=3,
        warnings=[],
    )
    print(f"Analyzed {report.overall.games_analyzed} games")
    print(f"ACPL: {report.overall.average_centipawn_loss}")
    print(f"HTML: {run_dir / 'report.html'}")
    print(f"JSON: {run_dir / 'analysis.json'}")


if __name__ == "__main__":
    main()
