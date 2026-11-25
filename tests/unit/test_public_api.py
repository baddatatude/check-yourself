"""Public PGN and command-line contract tests using a deterministic UCI stub."""

from __future__ import annotations

import json
import os
from concurrent.futures import Future
from pathlib import Path
from typing import Any

import chess
import chess.engine
import pytest
from typer.testing import CliRunner

from check_yourself import (
    AnalysisOptions,
    AnalysisResult,
    PGNError,
    StockfishError,
    analyze_game,
    analyze_games,
)
from check_yourself.cli import app
from check_yourself.reporting import render_html

FOOLS_MATE = """[White "Alice"]
[Black "Bob"]
[Result "0-1"]

1. f3 e5 2. g4 Qh4# 0-1
"""
REVERSED_NAMES = FOOLS_MATE.replace("Alice", "Temp").replace("Bob", "Alice").replace("Temp", "Bob")
BATCH = FOOLS_MATE + "\n" + REVERSED_NAMES


class StubUCI:
    id = {"name": "Stockfish Stub"}

    def __init__(self) -> None:
        self.config: dict[str, int] = {}
        self.quit_calls = 0
        self.close_calls = 0
        self.game_contexts: set[object] = set()
        self.returncode: Future[int] = Future()
        self.failure: str | None = None

    def configure(self, config: dict[str, int]) -> None:
        if self.failure == "configure":
            raise chess.engine.EngineError("rejected options")
        self.config = config

    def analyse(self, board: chess.Board, limit: chess.engine.Limit, **kwargs: Any) -> Any:
        self.game_contexts.add(kwargs["game"])
        if self.failure == "timeout":
            raise TimeoutError
        if self.failure == "search":
            raise chess.engine.EngineError("search failed")
        if board.is_checkmate():
            return [{"score": chess.engine.PovScore(chess.engine.Mate(0), board.turn)}]
        return [{
            "score": chess.engine.PovScore(chess.engine.Cp(12), chess.WHITE),
            "pv": list(board.legal_moves)[:1],
            "depth": limit.depth,
        }]

    def quit(self) -> None:
        self.quit_calls += 1
        if self.failure == "timeout":
            raise TimeoutError

    def close(self) -> None:
        self.close_calls += 1
        self.returncode.set_result(0)


@pytest.fixture
def uci(monkeypatch: pytest.MonkeyPatch) -> StubUCI:
    stub = StubUCI()
    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", lambda *_a, **_k: stub)
    monkeypatch.setattr("check_yourself.api.shutil.which", lambda _: "/example/stockfish")
    return stub


def test_named_perspective_replays_exact_moves_and_round_trips(uci: StubUCI) -> None:
    options = AnalysisOptions(depth=4, threads=2, hash_mb=32, pv_moves=3, timeout=2)
    result = analyze_games(BATCH, player=" aLiCe ", options=options)
    assert result.provenance.depth == 4
    assert result.provenance.stockfish_version == "Stockfish Stub"
    assert result.provenance.package_version
    assert result.provenance.timeout == 2
    assert result.schema_version == "1.1.0"
    assert result.player == "aLiCe"
    assert uci.config == {"Hash": 32, "Threads": 2}
    assert len(uci.game_contexts) == 2
    assert uci.quit_calls == uci.close_calls == 1
    assert [g.metadata.game_id for g in result.games] == ["game-1", "game-2"]
    assert [g.metadata.user_color for g in result.games] == ["white", "black"]
    assert result.overall.games_analyzed == 2
    assert (result.overall.wins, result.overall.losses) == (1, 1)
    move = result.games[1].moves[-1]
    assert (move.ply, move.played_uci, move.eval_after.display()) == (4, "d8h4", "+M0")
    board = chess.Board(move.fen_before)
    board.push_uci(move.played_uci)
    assert board.is_checkmate()
    assert move.fen_after == board.fen()
    board = chess.Board(move.fen_before)
    for uci_move in move.principal_variation_uci:
        board.push_uci(uci_move)
    assert AnalysisResult.model_validate_json(result.model_dump_json()) == result


def test_single_defaults_to_white_and_ignores_env(
    uci: StubUCI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CHECK_YOURSELF_DEPTH", "40")
    (tmp_path / ".env").write_text("CHECK_YOURSELF_THREADS=8\n", encoding="utf-8")
    result = analyze_game(FOOLS_MATE)
    assert result.provenance.depth == 12
    assert result.provenance.threads == 1
    assert result.games[0].metadata.user_color == "white"
    assert list(tmp_path.iterdir()) == [tmp_path / ".env"]
    assert uci.close_calls == 1


@pytest.mark.parametrize(
    ("pgn", "kwargs", "message"),
    [
        ("", {}, "No games"),
        ("malformed", {}, "no moves"),
        ("1. e5 *", {}, "illegal san"),
        ("[SetUp \"1\"]\n[FEN \"8/8/8/8/8/8/8/8 w - - 0 1\"]\n\n*", {}, "invalid starting"),
        ('[Variant "Atomic"]\n\n1. e4 *', {}, "only standard chess"),
        (FOOLS_MATE.replace('[Result "0-1"]', '[Result "1-0"]'), {}, "disagrees"),
        (BATCH, {}, "Expected one"),
        (FOOLS_MATE, {"player": "nobody"}, "was not found"),
        (FOOLS_MATE.replace('"Bob"', '"Alice"'), {"player": "Alice"}, "matches both"),
        (FOOLS_MATE, {"color": "black", "player": "Bob"}, "or a fixed color"),
    ],
)
def test_invalid_input_does_not_start_engine(
    pgn: str, kwargs: dict[str, Any], message: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("Started Stockfish for invalid input")

    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", unexpected)
    with pytest.raises(PGNError, match=message):
        analyze_game(pgn, **kwargs)


@pytest.mark.parametrize(
    ("failure", "message"),
    [("configure", "rejected options"), ("search", "search failed"), ("timeout", "exceeded")],
)
def test_engine_is_closed_after_failure(uci: StubUCI, failure: str, message: str) -> None:
    uci.failure = failure
    with pytest.raises(StockfishError, match=message):
        analyze_game(FOOLS_MATE)
    assert uci.quit_calls == uci.close_calls == 1
    assert uci.returncode.done()


def test_local_cli_writes_named_outputs(uci: StubUCI, tmp_path: Path) -> None:
    source = tmp_path / "batch.pgn"
    source.write_text(BATCH, encoding="utf-8")
    output = tmp_path / "review.json"
    html = tmp_path / "review.html"
    call = [
        "analyze-pgn", str(source), "--player", "Alice", "--depth", "4",
        "--output", str(output), "--html", str(html),
    ]
    cli = CliRunner()
    response = cli.invoke(app, call)
    assert response.exit_code == 0, response.output
    result = AnalysisResult.model_validate_json(output.read_text(encoding="utf-8"))
    assert result.provenance.depth == 4
    assert len(result.games) == 2
    if os.name == "posix":
        assert output.stat().st_mode & 0o077 == 0
        assert html.stat().st_mode & 0o077 == 0
    report = html.read_text(encoding="utf-8")
    assert "Stockfish Stub" in report and "CheckYourselfBoards.boot" in report
    assert "assets/logo" not in report and "assets/favicon" not in report
    assert isinstance(render_html(result), str)
    again = cli.invoke(app, call)
    assert again.exit_code == 2
    assert "already exists" in again.stderr
    assert source.read_text(encoding="utf-8") == BATCH


def test_local_cli_stdout_and_useful_input_error(uci: StubUCI, tmp_path: Path) -> None:
    source = tmp_path / "single.pgn"
    source.write_text(FOOLS_MATE, encoding="utf-8")
    cli = CliRunner()
    response = cli.invoke(app, ["analyze-pgn", str(source), "--color", "black"])
    assert response.exit_code == 0, response.output
    assert json.loads(response.stdout)["games"][0]["metadata"]["user_color"] == "black"
    source.write_text("1. e5 *", encoding="utf-8")
    response = cli.invoke(app, ["analyze-pgn", str(source)])
    assert response.exit_code == 2
    assert "illegal san" in response.stderr
    assert response.stdout == ""


def test_setup_fen_ply_is_relative_to_pgn(uci: StubUCI) -> None:
    pgn = (
        '[SetUp "1"]\n[FEN "8/8/8/8/8/6k1/5q2/7K b - - 0 20"]\n[Result "0-1"]'
        "\n\n20... Qg2# 0-1"
    )
    move = analyze_game(pgn, color="black").games[0].moves[0]
    assert (move.ply, move.fullmove_number, move.played_uci) == (1, 20, "f2g2")
    assert move.eval_after.display() == "+M0"


def test_missing_stockfish_is_a_cli_engine_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("check_yourself.api.shutil.which", lambda _: None)
    source = tmp_path / "single.pgn"
    source.write_text(FOOLS_MATE, encoding="utf-8")
    response = CliRunner().invoke(app, ["analyze-pgn", str(source)])
    assert response.exit_code == 3
    assert "not found on PATH" in response.stderr
    assert response.stdout == ""


def test_full_timeline_and_critical_continuations(uci: StubUCI) -> None:
    game = analyze_game(FOOLS_MATE, color="white").games[0]
    board = chess.Board()
    assert [row.ply for row in game.timeline] == [0, 1, 2, 3, 4]
    for row in game.timeline:
        if row.uci:
            assert row.san == board.san(board.parse_uci(row.uci))
            board.push_uci(row.uci)
        assert row.fen == board.fen()
        assert row.evaluation is not None
    assert game.timeline[-1].evaluation is not None
    assert game.timeline[-1].evaluation.display() == "-M0"
    assert [p.ply for p in game.timeline if p.critical] == [
        p.ply for p in game.timeline if any(c.ply == p.ply for c in game.critical_positions)
    ]
    for line in game.continuations:
        assert line.start_fen == game.timeline[line.ply - 1].fen
        for branch in (line.actual, line.recommended):
            board = chess.Board(line.start_fen)
            for step in branch:
                move = board.parse_uci(step.uci)
                assert step.san == board.san(move)
                board.push(move)
                assert step.fen == board.fen()
        assert all(step.evaluation is None for step in line.recommended)


def test_behavior_preserves_actual_samples_and_dates(uci: StubUCI) -> None:
    second = '[Date "2020.01.01"]\n' + REVERSED_NAMES
    first = '[Date "2021.01.01"]\n' + FOOLS_MATE
    result = analyze_games(first + "\n" + second, player="Alice")
    summary = result.behavior
    assert summary is not None
    assert (summary.games, summary.scored_moves, summary.known_result_games) == (2, 4, 2)
    assert [p.game_id for p in summary.dated_games] == ["game-2", "game-1"]
    assert [(p.color, p.games, p.moves) for p in summary.by_color] == [
        ("white", 1, 2), ("black", 1, 2)
    ]
    assert summary.advantageous_games == summary.converted_advantageous_games == 0
    assert result.tactics is not None
    assert AnalysisResult.model_validate_json(result.model_dump_json()).behavior == summary


def test_reads_previous_schema_without_interactive_fields(uci: StubUCI) -> None:
    data = analyze_game(FOOLS_MATE).model_dump()
    data["schema_version"] = "1.0.0"
    game = data["games"][0]
    for field in ("timeline", "continuations", "exercises"):
        del game[field]
    loaded = AnalysisResult.model_validate(data)
    assert loaded.schema_version == "1.0.0"
    assert loaded.games[0].moves
    assert not loaded.games[0].timeline
    assert not loaded.games[0].continuations
    assert not loaded.games[0].exercises



def test_internal_parser_rejection_becomes_pgn_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def rejected(*_args: object, **_kwargs: object) -> None:
        raise ValueError("parser conversion failed")
    monkeypatch.setattr("check_yourself.api.chess.pgn.read_game", rejected)
    with pytest.raises(PGNError, match="Game 1: could not parse PGN"):
        analyze_game(FOOLS_MATE)


def test_report_escapes_untrusted_player_label(uci: StubUCI) -> None:
    label = "Alice & <Club>"
    result = analyze_game(FOOLS_MATE.replace("Alice", label), player=label)
    html = render_html(result)
    assert "Alice &amp; &lt;Club&gt;" in html
    assert label not in html


def test_offline_report_embeds_pinned_basic_bundle_and_notices(uci: StubUCI) -> None:
    html = render_html(analyze_game(FOOLS_MATE))
    assert "plotly.js (basic - minified) v4.1.1" in html
    assert "Third-party chart licenses" in html
    assert "native-promise-only 0.8.1" in html
    assert "probe-image-size" not in html
