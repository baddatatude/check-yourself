# Check Yourself

**Check yourself before your rating wrecks itself.**

Review local chess games with Stockfish. Check Yourself connects each evaluation
to an exact position, lets you replay what happened alongside the engine's suggested
line, and turns critical positions into exercises. Its Python API returns structured
results for applications and scripts. Optional HTML reports work offline in a browser.

## Install

Use Python 3.11 or newer and install the Stockfish executable separately.
The supported Python versions are 3.11–3.14. On macOS
it is available through Homebrew as `stockfish`. On Ubuntu it is available as the
`stockfish` package and may be installed in `/usr/games`. Put the executable on
`PATH`, or pass its path with `--stockfish-path` or `AnalysisOptions.stockfish_path`.

Install in an activated virtual environment.

```sh
python -m pip install 'check-yourself-chess[html]==0.2.0'
check-yourself analyze-pgn --help
```

Omit `[html]` for Python analysis and JSON output.

## Review one game or a batch

With a local UTF-8 PGN file:

```sh
check-yourself analyze-pgn single.pgn --color black --depth 6 -o single.json
check-yourself analyze-pgn batch.pgn --player Alice --depth 6 -o batch.json --html batch.html
```

White is the default perspective. A named player can switch colors across the
batch. JSON goes to stdout unless an output file is provided. Output paths must
be new files. Open the HTML in your browser to select a graph point, compare
actual and recommended continuations, or try an exercise before revealing a solution.

To see both formats with synthetic games, run the fixture generator from the
source checkout and open `single.html` or `multi.html` in its output:

```sh
python tests/browser/generate_reports.py /tmp/check-yourself-examples
```

## Python API

```python
from check_yourself import AnalysisOptions, AnalysisResult, analyze_game

pgn = """[White "Alice"]
[Black "Bob"]
[Result "0-1"]

1. f3 e5 2. g4 Qh4# 0-1
"""
review = analyze_game(pgn, color="black", options=AnalysisOptions(depth=6))
last = review.games[0].timeline[-1]
assert last.uci == "d8h4"
assert last.evaluation is not None and last.evaluation.display() == "+M0"
assert AnalysisResult.model_validate_json(review.model_dump_json()) == review
```

See the [public API guide](docs/public-api.md) for batch analysis, offline HTML
and a backend integration example. See [JSON compatibility](docs/schema.md)
for the public and legacy formats.

## What the scores mean

Stockfish compares the played continuation with its preferred move at the
selected search depth. Average centipawn loss caps each move's contribution.
Mate distances are reported separately. Critical positions, game phases and
tactical patterns use heuristics. Batch reports show sample sizes and opening
labels only where available. Exercises confirm the saved recommendation and
all immediate mates. Other legal choices can remain ungraded.

Engine version, search settings and platform can influence the results. See
[metrics and limitations](docs/metrics.md) for definitions.

## Privacy and offline operation

The supported PGN workflow uses a local executable and needs no account, API
key, network access or profile. PGN headers and game data can appear in JSON or
HTML, so review reports before sharing them. On POSIX, the CLI creates named output files with owner-only access.
Use a private directory, especially when redirecting stdout. Use trusted Stockfish
binaries and reasonably sized PGN inputs. Server hosts should enforce their own
file, batch, time, and memory limits. Experimental connected commands
are isolated in the `[legacy]` extra and are outside this release's supported
local workflow. Legacy coaching sends game PGN content to its configured service
when requested.

## Licensing and contribution

See [project license](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md).
This distribution is GPL-3.0-or-later. Existing MIT grants are preserved in
[LICENSE.MIT](LICENSE.MIT). Stockfish and python-chess carry separate GPL licenses.
No Stockfish binary or opening-study dataset is bundled.

Development checks and local-engine tests are described in [CONTRIBUTING.md](CONTRIBUTING.md).
