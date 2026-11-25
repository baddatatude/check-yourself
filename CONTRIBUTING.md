# Contributing

Use an isolated Python environment and synthetic PGNs. Keep changes focused and
include regression tests for any change to scoring, replay or report behavior.
Use local Stockfish for the explicit integration checks. Do not commit personal
games, generated reports, or credentials.

From the source directory, in an activated environment:

```sh
python -m pip install -e '.[dev]'
ruff check src tests
mypy
python -m pytest
python -m pytest -o addopts= -q tests/integration/test_live.py::test_live_stockfish_probe tests/integration/test_stockfish_mate.py
```

The offline suite uses synthetic PGNs and mocked providers. The named integration
checks use a local engine and do not contact Chess.com. Release CI also exercises
base, HTML and legacy wheel installs with dependencies checked in fresh environments.
