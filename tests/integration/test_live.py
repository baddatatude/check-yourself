"""Optional integration tests (live network / real Stockfish)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from check_yourself.config import AnalysisSettings
from check_yourself.engine.stockfish import probe_stockfish
from check_yourself.pipeline import AnalysisPipeline
from check_yourself.providers.chess_com import HttpxChessComClient, probe_chess_com

pytestmark = pytest.mark.integration


@pytest.mark.integration
def test_live_chess_com_connectivity() -> None:
    ok, detail = probe_chess_com()
    assert ok, detail


@pytest.mark.integration
def test_live_stockfish_probe() -> None:
    if not shutil.which("stockfish"):
        pytest.skip("Stockfish not installed")
    ok, detail = probe_stockfish(None)
    assert ok, detail


@pytest.mark.integration
def test_live_fetch_one_game() -> None:
    ok, _ = probe_chess_com()
    if not ok:
        pytest.skip("Chess.com unreachable")
    with HttpxChessComClient() as client:
        games, _warnings = client.fetch_recent_games("hikaru", limit=1)
    assert len(games) == 1
    assert games[0].pgn


@pytest.mark.integration
def test_live_mini_analyze(tmp_path: Path) -> None:
    if not shutil.which("stockfish"):
        pytest.skip("Stockfish not installed")
    ok, _ = probe_chess_com()
    if not ok:
        pytest.skip("Chess.com unreachable")
    settings = AnalysisSettings(depth=6, default_output_dir=tmp_path)
    pipeline = AnalysisPipeline(settings=settings)
    report, run_dir = pipeline.run("hikaru", games=1, output_dir=tmp_path)
    assert report.overall.games_analyzed == 1
    assert (run_dir / "report.html").is_file()
