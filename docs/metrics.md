# Metrics

Check Yourself uses transparent Stockfish-based metrics. There is **no proprietary
accuracy score**.

# Centipawn loss (CPL)

For each move made by the requested player:

1. Evaluate the position **before** the move (White-POV from Stockfish).
2. Identify Stockfish’s preferred move and principal variation.
3. Play the **played** move and evaluate the resulting position.
4. If the preferred move differs, also evaluate the position after the preferred move.
5. Convert scores to the **player’s perspective**.
6. `eval_loss_cp = max(0, round(score_after_best − score_after_played))`
   when a preferred move is available; otherwise fall back to
   `max(0, round(before − after))`.

Before/after evaluations are always stored. Mate scores use a synthetic scale
(±100,000 adjusted by mate distance) and are **never** treated as ordinary
centipawn values for ranking mates vs cp positions.

That synthetic scale can make a single mate-blunder’s raw `eval_loss_cp` enormous
(tens of thousands). That is intentional for **quality labels** and **critical
position ranking**. It is **not** what you want in a simple average.

## Move quality labels

Configurable thresholds (defaults):

| Label | Evaluation loss |
|-------|-----------------|
| best | 0 |
| excellent | 1–10 |
| good | 11–25 |
| inaccuracy | 26–50 |
| mistake | 51–100, or above mistake threshold up to blunder |
| blunder | ≥ blunder threshold (default 200) |

Labels use the **raw** `eval_loss_cp` (mate-scale included).

## Average centipawn loss (ACPL)

Mean of per-move losses over the player’s moves in a game or across games.

For ACPL (and phase / opening averages derived from it), each move’s contribution
is **capped at 1000 cp** (`ACPL_LOSS_CAP_CP`). This keeps averages readable when a
few mate-transitions would otherwise dominate the mean.

**Median CPL** is also reported and is usually the better one-number summary of
typical move quality.

## Game phases

See `docs/game_phase.md`.

## Critical positions

Selected deterministically from large losses, winning→equal, winning/equal→losing,
missed wins/defenses, mate introductions, and turning points. Limited per game and
ranked by instructional importance (uses raw losses).

## Tactics heuristics

Piece/tactics counts (forks, pins, skewers, discovered attacks) are geometric
scans of opponent replies after tagged mistakes/blunders. They are directional
study aids, not an exhaustive tactics engine.
