"""Create synthetic report fixtures for the Chrome interaction checks."""

from __future__ import annotations

import argparse
from pathlib import Path

from check_yourself import AnalysisOptions, analyze_games
from check_yourself.reporting import render_html

GAME = """[White "Alice"]
[Black "Bob"]
[Date "2025.01.02"]
[Result "0-1"]

1. f3 e5 2. g4 Qh4# 0-1"""
RETURN_GAME = """[White "Bob"]
[Black "Alice"]
[Date "2025.01.03"]
[Result "0-1"]

1. f3 e5 2. g4 Qh4# 0-1"""
MATE_CHOICE = """[White "Alice"]
[Black "Bob"]
[Date "2025.01.04"]
[SetUp "1"]
[FEN "7k/5Q2/6K1/8/8/8/8/8 w - - 0 1"]
[Result "*"]

1. Qg8+ *"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--browser-check", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, pgn in (("single", GAME), ("multi", "\n\n".join((GAME, RETURN_GAME, MATE_CHOICE)))):
        result = analyze_games(pgn, player="Alice", options=AnalysisOptions(depth=6))
        html = render_html(result)
        (args.output / f"{name}.html").write_text(html, encoding="utf-8")
        if args.browser_check:
            script = args.browser_check.read_text(encoding="utf-8")
            (args.output / f"{name}-browser.html").write_text(
                html.replace("</body>", f"<script>{script}</script></body>"), encoding="utf-8"
            )


if __name__ == "__main__":
    main()
