# Local PGN analysis

Install `check-yourself-chess` and install the Stockfish executable separately. Put Stockfish on `PATH` or pass an explicit path. Install `check-yourself-chess[html]` for offline HTML. The analysis path has no network or credential requirement and does not read `.env`, create profiles, write files, or load opening-study data.

## Python

```python
from check_yourself import AnalysisOptions, AnalysisResult, analyze_game, analyze_games

fools_mate = """[White "Alice"]
[Black "Bob"]
[Result "0-1"]

1. f3 e5 2. g4 Qh4# 0-1
"""
return_game = """[White "Bob"]
[Black "Alice"]
[Result "0-1"]

1. f3 e5 2. g4 Qh4# 0-1
"""
options = AnalysisOptions(depth=6, threads=1, hash_mb=16)
single = analyze_game(fools_mate, color="black", options=options)
last = single.games[0].moves[-1]
assert (last.ply, last.played_uci, last.eval_after.display()) == (4, "d8h4", "+M0")

batch = analyze_games(fools_mate + "\n" + return_game, player="Alice", options=options)
assert [g.metadata.user_color for g in batch.games] == ["white", "black"]
assert batch.overall.games_analyzed == 2
payload = batch.model_dump_json(indent=2)
assert AnalysisResult.model_validate_json(payload) == batch
```

Both calls accept PGN **text** and return an `AnalysisResult` envelope. Pass `color="white"` or `color="black"` to score a fixed side. White is the default. Pass `player` instead to select exactly one matching White or Black header per game, with case-insensitive matching. A missing or ambiguous player fails with the game's ordinal. Games are replayed sequentially and returned in input order. Read local files with `Path.read_text(encoding="utf-8-sig")` for UTF-8 and optional BOM.

Standard-chess games with a valid setup FEN are supported. Scoring follows the main line. Games with no moves, unsupported variants, invalid initial boards and errors reported by the python-chess parser are rejected. The parser accepts normal PGN comments and annotations and can ignore unrecognized tokens. It is not a strict grammar validator. An unfinished but playable PGN can be analyzed and has no win/loss/draw result when its result is `*`. Results otherwise follow the PGN result, including games decided by resignation.

Catch `PGNError` for unusable input, `StockfishError` for missing engines, rejected engine options, and search failures, or their common base `AnalysisError`. Creating invalid `AnalysisOptions` raises Pydantic `ValidationError`. All games and perspectives are validated before engine startup. No partial analysis is returned when a call fails. Each call owns one process, uses a new UCI game context per game, and closes the process on success or failure. `timeout` bounds individual UCI operations and is not a wall-clock budget for an entire batch.

The supported surface is `analyze_game`, `analyze_games`, their options, result and error types exported from `check_yourself`, and `check_yourself.reporting.render_html` and `ReportError`. Engine adapters, provider modules, legacy pipelines, profile stores and the internal HTML view model are implementation details.

## Results and reproducibility

Public JSON schema `1.1.0` adds the timeline, continuations, exercises and optional cross-game behavior and tactics. Older `1.0.0` JSON remains readable and its missing fields default to empty or null. The public envelope is separate from legacy report JSON. It identifies the package and reported Stockfish version, requested depth, threads, hash size, one search line, PV length, timeout, and critical-position limit. It has no run timestamp or local executable path. Each `game_id` is an ordinal within that input collection. Use `(game_id, ply)` for a move key and your own persistent game identifier when storing results across runs. A ply is one-based relative to the PGN's main line, even for a custom FEN. Both pre-move and post-move FENs are provided. The evaluation fields use the scored player's perspective, with White-perspective values retained. `mate_for_player` disambiguates mate at distance zero. See [the scoring notes](metrics.md).

The engine's outputs can vary with Stockfish build and version, platform, search settings, scheduling with multiple threads, and UCI behavior. Fixed settings and one thread make comparisons easier. They do not guarantee identical evaluations or byte-identical results across hosts. HTML rendering also generates Plotly element IDs.

## Backend integration example

This function accepts a completed standard-chess PGN from an application that has already authenticated the request and bounded the workload. The adapter returns JSON-ready data and leaves transport and request scheduling to the host.

```python
from typing import Literal

from check_yourself import AnalysisOptions, analyze_game

def review_completed_game(pgn: str, side: Literal["white", "black"]) -> dict:
    result = analyze_game(pgn, color=side, options=AnalysisOptions(depth=10))
    game = result.games[0]
    by_ply = {move.ply: move for move in game.moves}
    return {
        "schema_version": result.schema_version,
        "provenance": result.provenance.model_dump(mode="json"),
        "game_id": game.metadata.game_id,
        "critical": [
            {
                "ply": moment.ply,
                "fen_before": by_ply[moment.ply].fen_before,
                "fen_after": by_ply[moment.ply].fen_after,
                "played_uci": moment.played_uci,
                "alternative_uci": moment.preferred_uci,
                "pv_uci": by_ply[moment.ply].principal_variation_uci,
                "evaluation": moment.eval_after.model_dump(mode="json"),
                "reasons": [reason.value for reason in moment.reasons],
            }
            for moment in game.critical_positions
        ],
    }
```

## Offline HTML and CLI

```python
from pathlib import Path

from check_yourself.reporting import render_html

# 'batch' is the result from the Python example above.
Path("review.html").write_text(render_html(batch), encoding="utf-8")
```

```sh
check-yourself analyze-pgn single.pgn --color black --depth 6
check-yourself analyze-pgn games.pgn --player Alice --depth 8 \
  --output review.json --html review.html
check-yourself analyze-pgn --help
```

JSON goes to stdout unless `--output` is supplied. `--html` writes a standalone HTML file. File destinations must be distinct, have existing parent directories, and be new files. The command never uses PGN metadata to generate a filename. Exit codes are 0 for success, 2 for usage, PGN, output or missing HTML-extra errors, and 3 for Stockfish failures. Errors go to stderr. The experimental `analyze`, `coach` and `doctor` commands are preserved behind the `[legacy]` extra. These are separate from the supported offline workflow.


## Interactive report and training data

- `game.timeline` records the starting FEN at ply 0 and the FEN after every mainline ply. A score belongs to that exact position and uses the selected player's perspective. Before/after searches for the selected color also cover most opponent plies. At most two extra searches fill uncovered boundary positions. A final checkmate is determined from the board and retains mate polarity. Move quality is present only for the selected player's scored moves. Mate positions appear as separate selectable events because a mating distance has no centipawn equivalent. The evaluation bar uses a bounded display scale. Its number is the saved score, and its fill is not a win probability.
- `game.continuations` connects each critical ply to the position **before** it. The actual mainline and hypothetical engine PV each contain UCI, SAN and the FEN after the move. The actual branch retains measured position scores. The hypothetical branch contains no inferred per-step scores. Both branches are bounded by the configured PV length. Their construction does not call Stockfish again.
- `result.behavior` describes batches by color with game and scored-move counts and capped ACPL. `result.overall` has color records, heuristic phase aggregates and opening statistics from PGN labels. Unknown openings stay unknown. The dated observations use complete PGN dates, omit unknown dates, and retain collection order for tied dates. Compare only samples with enough games and similar conditions. No improvement trend is inferred automatically.
- A **lost detected mate** is a player's move from an engine-reported favorable mate to a position without one. A **newly detected forced mate against the player** is the inverse defensive event. These are depth-dependent transitions and do not establish why an error happened. The conversion denominator uses completed games with at least one evaluated pre-move advantage of 200 cp or a favorable mate. The numerator counts wins in that group. Counts describe this sample and do not estimate a general conversion rate.
- `result.tactics` counts candidate opponent motifs spotted after mistakes and blunders via legal replies and board geometry. These are heuristic signals. A motif may overlap with others, and its presence is not proof that it was played, was best, or caused the loss. Use the existing `errors_scanned` denominator and inspect the included examples before drawing conclusions.
- `game.exercises` records a source game/ply, perspective, starting FEN, reference evaluation, legal candidate UCI/SAN and confirmed lines. Exercises come from critical moves with nonzero loss and a saved PV. The saved recommendation is supported at the analyzed depth. Every immediately mating legal move is accepted independently of PV ordering. The offline report leaves other legal moves ungraded and lets the user reveal the saved lines. It assigns no difficulty or unverified theme. Training data requires no extra engine searches or persistent profile.
