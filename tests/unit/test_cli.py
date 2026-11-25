"""CLI tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from check_yourself.cli import app

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "analyze" in result.stdout
    assert "coach" in result.stdout
    assert "doctor" in result.stdout


def test_coach_missing_report() -> None:
    result = runner.invoke(app, ["coach", "--from-report", "missing-report-dir", "--no-llm"])
    assert result.exit_code == 2
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Error" in combined or "not found" in combined.lower() or "No analysis" in combined


def test_analyze_invalid_username() -> None:
    result = runner.invoke(app, ["analyze", "ab", "--games", "1"])
    assert result.exit_code == 2
    assert "Invalid" in result.stdout or "Invalid" in (result.stderr or "")


def test_analyze_missing_stockfish() -> None:
    with patch(
        "check_yourself.cli.AnalysisSettings.resolve_stockfish_path",
        return_value=None,
    ):
        result = runner.invoke(app, ["analyze", "cooperharris", "--games", "1"])
    assert result.exit_code == 3
    assert "Stockfish" in result.stdout or "Stockfish" in (result.stderr or "")


def test_doctor_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "check_yourself.providers.chess_com.probe_chess_com", lambda *_: (True, "mocked")
    )
    monkeypatch.setattr(
        "check_yourself.providers.lichess.probe_lichess", lambda *_: (True, "mocked")
    )
    existing = tmp_path / ".check_yourself_write_probe"
    existing.write_text("keep", encoding="utf-8")
    result = runner.invoke(app, ["doctor", "--output", str(tmp_path)])
    assert existing.read_text(encoding="utf-8") == "keep"
    assert list(tmp_path.iterdir()) == [existing]
    # The local Stockfish probe may fail on hosts without the executable.
    assert "Python / package" in result.stdout
    assert "Stockfish" in result.stdout
    assert "Chess.com" in result.stdout
    assert "Lichess" in result.stdout


def test_analyze_unsupported_platform() -> None:
    result = runner.invoke(
        app,
        ["analyze", "testplayer", "--platform", "chess24", "--games", "1"],
    )
    assert result.exit_code == 2
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Unsupported platform" in combined
    assert "lichess" in combined.lower()
