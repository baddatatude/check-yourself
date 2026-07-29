# Check Yourself

**Check yourself before your rating wrecks itself.**

Check Yourself is a local Python package that downloads a Chess.com or Lichess
player’s recent games, analyzes them with Stockfish, finds critical mistakes and
cross-game habits, and writes a self-contained HTML report you open in a browser.

There is **no separate interactive web server** in this repo yet. The “webapp”
today is the generated `report.html` file (offline, no CDN). A live dashboard is
on the Stage 3 roadmap.

This project is **not affiliated with Chess.com, Lichess, or Stockfish**.

**Version:** 0.2.0 (alpha)

---

## What you get

| Piece | What it is |
|-------|------------|
| **Package / CLI** | `check-yourself` — fetch, analyze, coach, write artifacts |
| **HTML report** | Browser UI: charts, interactive boards, habits, tactics, optional AI coaching |
| **JSON artifacts** | Machine-readable `analysis.json` + per-game caches |
| **Player profile** | Durable coaching memory under `players/` across sessions |

---

## How the package works

```text
check-yourself analyze
        │
        ▼
  GameSource (--platform chess.com | lichess)
        │  newest N public games + PGNs
        ▼
  Stockfish (local engine, optional --workers)
        │  per-move eval loss for the requested player
        ▼
  Aggregates + habits + piece/tactics
        │  ACPL (capped), phases, openings, patterns, motifs
        ▼
  Optional OpenAI coaching (--coach)
        │  grounded on Stockfish + habit/tactics briefs + prior profile
        ▼
  reports/USERNAME-TIMESTAMP/
        ├── report.html      ← open in browser
        ├── analysis.json
        └── games/*.pgn + *.json
  players/USERNAME__PLATFORM/profile.json   ← durable memory
```

### CLI commands

| Command | Purpose |
|---------|---------|
| `check-yourself analyze USERNAME` | Fetch + Stockfish analyze + write report |
| `check-yourself coach --from-report PATH` | Re-coach from saved `analysis.json` (no Stockfish) |
| `check-yourself doctor` | Check Stockfish, Chess.com, Lichess, API key, write access |

### Analyze pipeline (detail)

1. **Platform** — `--platform chess.com` or `--platform lichess` (default `chess.com`). Unsupported values error out; no auto-detect.
2. **Fetch** — Newest *N* eligible games from the public API (optional `--time-control`).
3. **Cache** — PGNs under `reports/.../games/`.
4. **Engine** — Analyze only the requested player’s moves with local Stockfish (`--depth`, `--workers`).
5. **Metrics** — ACPL (per-move loss capped at 1000 cp for averages), median CPL, phase/opening aggregates, pattern indicators.
6. **Habits** — Deterministic cross-game weaknesses.
7. **Tactics** — Checkmate piece, blunder piece, approximate fork/pin/skewer/discovered-attack motifs.
8. **Coaching (optional)** — If `--coach`, send an engine-grounded brief to OpenAI; **never store the API key in reports**.
9. **Outputs** — `report.html`, `analysis.json`, update `players/.../profile.json`.

### Re-coach without re-analyzing

```bash
check-yourself coach --from-report reports/USERNAME-TIMESTAMP --no-llm
check-yourself coach --from-report reports/USERNAME-TIMESTAMP/analysis.json
```

---

## How the HTML report (web UI) works

The report is a **single self-contained HTML file**. Plotly.js and a small SVG board
script are embedded so charts and boards work offline (no server, no CDN).

### What’s on the page

| Section | Source |
|---------|--------|
| Header | Player, platform, depth, time |
| AI coaching | Present only if `--coach` succeeded |
| Coach walkthrough | Click-through boards for swings / habits / themes / tactics |
| Error heatmaps | Where mistakes/blunders originate or land |
| Player summary | Record, median CPL, capped ACPL, error rates |
| Visualizations | Plotly charts including piece/tactics bars |
| Phase / opening tables | Aggregates |
| Pattern indicators | Winning spoiled, equal→lost, etc. |
| Pieces & tactics | Mating pieces, blunder pieces, motif examples |
| Habits & weaknesses | Deterministic habit analyzer + boards |
| Per-game details | Eval graph, critical boards, coaching notes |

---

## Installation

Requires **Python 3.11+** and a local **Stockfish** binary.

```bash
git clone <this-repo> check-yourself
cd check-yourself
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

Dev extras: `pip install -e ".[dev]"`.

### Stockfish setup

**macOS:** `brew install stockfish`  
**Linux (Debian/Ubuntu):** `sudo apt install stockfish`  
**Windows:** download from [stockfishchess.org/download](https://stockfishchess.org/download/), then `--stockfish-path` or `PATH`.

Verify with `check-yourself doctor`.

---

## Quick start

```bash
check-yourself analyze USERNAME --games 10
check-yourself analyze USERNAME --platform lichess --games 10 --workers 4
```

### Optional AI coaching

```bash
cp .env.example .env   # then edit .env — do not commit .env
# or: export OPENAI_API_KEY=sk-...
check-yourself analyze USERNAME --games 20 --workers 4 --coach
```

Default model: `gpt-4.1-mini`. Prefer env / `.env` over `--openai-api-key`.

---

## Secrets & security

- **Never commit** `.env`, API keys, or real credentials. `.gitignore` already excludes
  `.env`, `.env.*` (except `.env.example`), `reports/`, and `players/`.
- Copy `.env.example` → `.env` and fill `OPENAI_API_KEY` locally if you use `--coach`.
- The key is read from the environment / `.env` / a hidden prompt; it is **never**
  written into `analysis.json`, HTML reports, fixtures, or profiles.
- Prefer `OPENAI_API_KEY` in `.env` over passing `--openai-api-key` (avoids shell history).
- If a key is ever committed or leaked, **rotate it immediately** in the OpenAI dashboard.

---

## Privacy

- Uses Chess.com’s and Lichess’s **public** APIs only.
- Games and reports stay **local** under `reports/` and `players/` (gitignored).
- No account passwords are stored.
- Optional OpenAI coaching sends compact engine-grounded summaries when enabled.

---

## Calculated metrics

See [docs/metrics.md](docs/metrics.md).

- **Median CPL** — robust one-number summary of typical move quality  
- **Avg ACPL** — mean of per-move losses, each capped at **1000 cp** (mate-scale raw losses still used for blunder labels / critical ranking)  
- Inaccuracies / mistakes / blunders, phase & opening aggregates, habits, tactics heuristics  

There is **no proprietary “accuracy” score**.

---

## Architecture

See [docs/architecture.md](docs/architecture.md).

```text
CLI → GameSource → PGN cache → Stockfish
    → aggregates / habits / tactics
    → HTML (charts + boards) + analysis.json
    → optional OpenAI coaching + players/profile.json
```

---

## Development

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
mypy
pytest                 # offline suite (default)
pytest -m integration  # optional live network / Stockfish
python examples/run_fixture_analysis.py
```

---

## Roadmap

| Stage | Scope |
|-------|--------|
| **1–2 (0.2.0)** | CLI, Chess.com + Lichess, Stockfish, HTML/JSON, habits, tactics, boards, optional coaching + profiles |
| **3** | Local interactive dashboard (consumes `analysis.json`) |
| **4** | Optional MCP interface and public-package polish |

---

## Disclaimer

Check Yourself is an independent open-source project. It is **not affiliated with,
endorsed by, or associated with Chess.com, Lichess, or Stockfish**. Those names are
used only to describe compatibility with publicly available APIs and engines.

Engine evaluations are imperfect. Treat reports as study aids, not absolute truth.

---

## License

MIT — see [LICENSE](LICENSE).
