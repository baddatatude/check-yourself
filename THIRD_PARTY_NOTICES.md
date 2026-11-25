# Third-party notices

## Embedded Plotly.js basic 4.1.1

Generated HTML embeds the official reduced Plotly.js bundle under MIT and
retains the applicable upstream notices in the report footer. The wheel and
sdist contain the pinned browser bundle and its complete collected notices in
`check_yourself/reports/static/plotly-basic-NOTICES.txt` inside the Python
package. Upstream corresponding sources and build inputs are available in
the [Plotly.js v4.1.1 source tree](https://github.com/plotly/plotly.js/tree/v4.1.1).
The npm distribution is
[`plotly.js-basic-dist-min@4.1.1`](https://www.npmjs.com/package/plotly.js-basic-dist-min/v/4.1.1).
The bundled script has SHA-256
`99784e3abfb07b142a15e521a439e6d9addceadb3f79553fd24c72774f0649ba`.
Python Plotly is installed separately with the HTML extra. Reports do not
embed the full browser bundle carried by that Python dependency.

## Separately installed dependencies

- **python-chess** (`chess`) is GPL-3.0-or-later. Its source and license are
  available from [python-chess](https://github.com/niklasf/python-chess).
- **Stockfish** runs as a separately installed GPLv3 UCI process.
  Check Yourself bundles no engine executable or neural-network weights.
  [Upstream source and license](https://github.com/official-stockfish/Stockfish).
- **Jinja2** and **MarkupSafe** are BSD-3-Clause packages.
  [Jinja](https://github.com/pallets/jinja) · [MarkupSafe](https://github.com/pallets/markupsafe).

See `LICENSE.MIT` for the preserved historic project notice.
