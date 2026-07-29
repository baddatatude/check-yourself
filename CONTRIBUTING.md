# Contributing

Thanks for your interest in Check Yourself.

## Development setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Checks

```bash
ruff check src tests
mypy
pytest
```

Live integration tests (optional):

```bash
pytest -m integration
```

## Guidelines

- Optional Stage 2 coaching (`--coach`) is allowed; do not add a live dashboard or MCP
  unless a roadmap stage explicitly requests it.
- Prefer dependency injection for the game source, engine adapter, coaching
  provider, and report writers.
- Offline tests must not require network access, a real Stockfish binary, or a live
  OpenAI API key.
- Never write API keys into reports, fixtures, logs, or commits. Keep secrets in
  local `.env` only (see `.env.example`).
- Document evaluation, ACPL capping, and phase-classification methods when you change them.
- Keep tactics motif language honest: geometric heuristics, not a puzzle engine.

## Pull requests

1. Keep changes focused.
2. Add or update tests.
3. Run Ruff, mypy, and the offline pytest suite before opening a PR.
