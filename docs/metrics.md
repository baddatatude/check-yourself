# Metrics

Check Yourself uses transparent Stockfish-based metrics. There is **no proprietary
accuracy score**.

# Centipawn loss (CPL)

For each move made by the requested player:

1. Evaluate the position **before** the move (White-POV from Stockfish).
2. Identify Stockfish’s preferred move and principal variation.
3. Play the **played** move and evaluate the resulting position.
4. If the preferred move differs, also evaluate the position after the preferred move.
   Both continuations retain the replayed move history. Playing the exact preferred
   move yields zero loss. Another move reaching an equally scored continuation
   also yields zero loss.
5. Convert scores to the **player’s perspective**.
6. `eval_loss_cp = max(0, round(score_after_best − score_after_played))`
   when a preferred move is available; otherwise fall back to
   `max(0, round(before − after))`.

Before/after evaluations keep the score kind and player perspective. For a
centipawn score, `value` is signed from the player's point of view and `white_cp`
retains the engine score from White's point of view. For a mate score, `value`
is signed mate distance in moves and `white_mate` is the White-perspective
distance. At checkmate both distances are zero. Report schema 1.6.0 adds
`mate_for_player` to distinguish a mate delivered (`true`) from a mate suffered
(`false`), including at distance zero. A legacy zero-mate row without this field
has an unknown winner and displays as `M0`.

For ranking, mates use ±100,000 reduced in magnitude by mate distance. A
delivered checkmate has the full positive score and a suffered checkmate the
full negative score. These are synthetic ranking values. The reported evaluation
still has kind `mate` and its original distance.

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
| mistake | 51–199 |
| blunder | ≥ 200 |

Labels use the **raw** `eval_loss_cp` (mate-scale included). The separate
`mistake_threshold` (default 100) is also used by critical-position and habit
selection.

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
