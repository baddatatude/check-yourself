# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] — 2026-07-27

### Added

- Interactive HTML board aids: coach walkthroughs (themes/habits/critical swings),
  error heatmaps, and inline boards with played vs preferred arrows.
- Piece & tactics breakdown: which pieces checkmate you, which pieces you blunder
  with most, and approximate fork / pin / skewer / discovered-attack motifs after
  mistakes (`tactics` on analysis schema `1.4.0`).
- Brand assets in reports (logo watermark + favicon).

### Changed

- **ACPL averages** now cap each move’s contribution at **1000 cp** so mate-scale
  synthetic losses no longer inflate Avg ACPL into thousands. Raw per-move
  `eval_loss_cp` is unchanged for blunder labels and critical-position ranking.
  Median CPL is surfaced prominently in the CLI and HTML summary.
- Tactics section labeled as an approximate geometric heuristic (not a puzzle engine).
- Docs refreshed: architecture, metrics, README security note, contributing notes.

### Schema

- Analysis report schema **1.4.0** (`tactics` optional section).

## [0.1.0] — 2026-07-23

### Added

- Stage 1 engine-only vertical slice:
  - `check-yourself analyze USERNAME` downloads recent Chess.com games, analyzes
    them with Stockfish, and writes HTML + JSON reports.
  - `check-yourself doctor` environment checks.
  - Transparent metrics (ACPL, inaccuracies/mistakes/blunders, phase and opening
    aggregates, pattern indicators).
  - Offline unit tests and optional live integration tests.
- `--workers` for parallel Stockfish game analysis (sequential fallback on failure).
- Optional Stage 2 coaching: `--coach` with OpenAI (`gpt-4.1-mini` default),
  grounded on Stockfish critical positions; API keys never written to reports.
- Analysis schema `1.1.0` with optional `coaching` section.
- Lichess support via explicit `--platform chess.com|lichess` (unsupported platforms
  error out; no auto-detect). Analysis schema `1.2.0` records `platform`.
- Deterministic cross-game habit analyzer (`Habits & weaknesses` in HTML + coaching
  `habit_brief`). Schema `1.3.0`.
- Durable player coaching profiles under `players/` plus
  `check-yourself coach --from-report` to re-coach without re-running Stockfish.
