# Architecture overview

```text
CLI (Typer) --platform chess.com|lichess
  └─ AnalysisPipeline
       ├─ GameSource (providers/)
       │    ├─ HttpxChessComClient  — monthly archives → newest N games
       │    └─ HttpxLichessClient   — NDJSON export → newest N games
       ├─ StockfishEngine (engine/)        — UCI analyse + eval normalization
       ├─ GameAnalyzer    (analysis/)      — per-player-move metrics
       ├─ critical_positions / game_phase / aggregate
       ├─ habit_analyzer / tactics_analyzer
       ├─ optional OpenAI coaching (providers/coaching.py;
       │     habit_brief + tactics_brief + prior_profile)
       └─ reports/ + visualization/        — HTML (Plotly + SVG boards) + JSON
```

## Platforms

- Users choose the site explicitly with `--platform` / `-p` (`chess.com` or `lichess`).
- Unsupported values raise a clear error (no auto-detect).
- Shared PGN helpers live in `providers/pgn_utils.py`.

## Habit analysis

- `analysis/habit_analyzer.py` computes deterministic weaknesses across the sample
  (conversion leaks, equal→lost, phase-concentrated blunders, late-game errors,
  mate motifs, high-loss openings, color imbalance).
- Findings always appear in the HTML report; `--coach` sends them as `habit_brief`
  so the LLM explains evidence rather than inventing patterns.

## Piece & tactics analysis

- `analysis/tactics_analyzer.py` summarizes:
  - pieces that **checkmated** the player (terminal mate only),
  - pieces the player **moved** when Stockfish tagged a blunder,
  - approximate **fork / pin / skewer / discovered attack** motifs available to the
    opponent after mistakes/blunders (geometric heuristics, not a puzzle engine).
- Results appear under **Pieces & tactics** in HTML and as `tactics_brief` for coaching.

## Interactive report boards

- `visualization/walkthrough.py` builds click-through sequences (biggest swings,
  habits, coaching themes, tactic examples) and square heatmaps.
- `reports/static/board.js` renders offline SVG boards with played (red) vs
  preferred (green) arrows — no CDN.

## Durable coaching memory

- Per-player profiles live at `players/<username>__<platform>/profile.json`.
- Profiles store recurring habits, themes, practice focus, and recent coach narratives.
- `check-yourself coach --from-report PATH` reloads `analysis.json`, optionally calls
  the LLM with `prior_profile`, updates HTML/JSON, and merges into the durable profile
  — without re-running Stockfish.

## Extension points

| Feature | Hook |
|---------|------|
| OpenAI coaching | `providers/coaching.py` (`OpenAICoachingProvider`) + `--coach` |
| Local dashboard | consume `analysis.json` / report folder; no analysis rewrite |
| MCP server | thin adapter over `AnalysisPipeline` and report paths |

### Coaching notes

- Coaching is **optional** and grounded on Stockfish critical positions / error moves.
- API keys are read from `OPENAI_API_KEY` / `CHECK_YOURSELF_OPENAI_API_KEY` or a hidden prompt.
- Keys are never written into `analysis.json`, HTML reports, or logs.

Dependency injection is used for the game source, engine adapter, coaching provider,
and report output paths so later stages can swap implementations without rewriting
the pipeline.
