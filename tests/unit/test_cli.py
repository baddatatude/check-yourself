"""CLI tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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


def test_doctor_runs(tmp_path: Path) -> None:
    result = runner.invoke(app, ["doctor", "--output", str(tmp_path)])
    # May fail Stockfish or network in CI; still should produce table output
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
