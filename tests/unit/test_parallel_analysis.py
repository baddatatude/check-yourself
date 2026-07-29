"""Parallel Stockfish worker pool and sequential fallback tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from tests.fixtures.mock_engine import ScriptedLossEngine
from tests.fixtures.sample_data import SAMPLE_PGN_BLACK, SAMPLE_PGN_RAPID, SAMPLE_PGN_WHITE

from check_yourself.config import AnalysisSettings
from check_yourself.engine.stockfish import EngineError
from check_yourself.pipeline import _analyze_games_parallel, analyze_game_batch
from check_yourself.providers.chess_com import parse_pgn_metadata


def _sample_metas() -> list:
    metas = []
    for pgn, end in (
        (SAMPLE_PGN_WHITE, 1),
        (SAMPLE_PGN_BLACK, 2),
        (SAMPLE_PGN_RAPID, 3),
    ):
        meta = parse_pgn_metadata(pgn, username="TestPlayer", end_time=end)
        assert meta is not None
        metas.append(meta)
    return metas


def test_parallel_preserves_order(tmp_path: Path) -> None:
    settings = AnalysisSettings(depth=2, workers=2)
    metas = _sample_metas()
    engines = [ScriptedLossEngine(), ScriptedLossEngine()]

    results = _analyze_games_parallel(
        metas,
        settings,
        workers=2,
        games_dir=tmp_path,
        engines=engines,
    )

    assert len(results) == 3
    assert [r.metadata.game_id for r in results] == [m.game_id for m in metas]
    assert all((tmp_path / f"{r.metadata.game_id}.json").is_file() for r in results)


def test_analyze_batch_falls_back_when_pool_fails(tmp_path: Path) -> None:
    settings = AnalysisSettings(depth=2, workers=4)
    metas = _sample_metas()
    warnings: list[str] = []

    class OpenableScripted(ScriptedLossEngine):
        def open(self) -> None:
            return None

    sequential_engine = OpenableScripted()

    with (
        patch(
            "check_yourself.pipeline._analyze_games_parallel",
            side_effect=EngineError("could not start Stockfish pool"),
        ),
        patch(
            "check_yourself.pipeline.StockfishEngine.from_settings",
            return_value=sequential_engine,
        ),
    ):
        results = analyze_game_batch(
            metas,
            settings=settings,
            games_dir=tmp_path,
            workers=4,
            warnings=warnings,
        )

    assert len(results) == 3
    assert any("falling back to sequential" in w for w in warnings)


def test_analyze_batch_uses_injected_engine_sequentially(tmp_path: Path) -> None:
    settings = AnalysisSettings(depth=2, workers=4)
    metas = _sample_metas()
    engine = ScriptedLossEngine()

    with patch("check_yourself.pipeline._analyze_games_parallel") as parallel:
        results = analyze_game_batch(
            metas,
            settings=settings,
            games_dir=tmp_path,
            engine=engine,
            workers=4,
        )
        parallel.assert_not_called()

    assert len(results) == 3


def test_open_engine_pool_closes_on_partial_failure() -> None:
    from check_yourself.pipeline import _open_engine_pool

    settings = AnalysisSettings()
    opened: list[object] = []

    class BoomEngine:
        def open(self) -> None:
            if len(opened) >= 1:
                raise EngineError("second worker failed")
            opened.append(self)

        def close(self) -> None:
            opened.remove(self)

    with patch(
        "check_yourself.pipeline.StockfishEngine.from_settings",
        side_effect=lambda _s: BoomEngine(),
    ), pytest.raises(EngineError, match="second worker"):
        _open_engine_pool(settings, workers=2)

    assert opened == []
