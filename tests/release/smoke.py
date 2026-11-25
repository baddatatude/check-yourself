"""Installed API checks using synthetic PGNs and a local Stockfish process."""

from __future__ import annotations

import sys
from importlib.util import find_spec
from pathlib import Path

import check_yourself
from check_yourself import AnalysisOptions, AnalysisResult, analyze_game, analyze_games

assert Path(check_yourself.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert all(find_spec(name) is None for name in ("httpx", "jinja2", "plotly"))
first = '[White "Alice"]\n[Black "Bob"]\n[Result "0-1"]\n\n1. f3 e5 2. g4 Qh4# 0-1'
second = '[White "Bob"]\n[Black "Alice"]\n[Result "0-1"]\n\n1. f3 e5 2. g4 Qh4# 0-1'
settings = AnalysisOptions(depth=6)
result = analyze_game(first, color="black", options=settings)
mate = result.games[0].timeline[-1]
assert mate.ply == 4 and mate.uci == "d8h4"
assert mate.evaluation is not None and mate.evaluation.display() == "+M0"
batch = analyze_games(first + "\n\n" + second, player="Alice", options=settings)
assert [game.metadata.user_color for game in batch.games] == ["white", "black"]
assert batch.behavior and batch.behavior.scored_moves == 4
assert AnalysisResult.model_validate_json(batch.model_dump_json()) == batch
Path("single.pgn").write_text(first + "\n", encoding="utf-8")
Path("batch.pgn").write_text(first + "\n\n" + second + "\n", encoding="utf-8")
print("Installed core API smoke passed")
