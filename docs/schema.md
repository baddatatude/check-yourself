# JSON formats and compatibility

| Format | Entry point | Versions |
|---|---|---|
| Public local analysis | `analyze_game`, `analyze_games`, `analyze-pgn` | Emits 1.1.0. Reads 1.0.0 and 1.1.0 with `AnalysisResult.model_validate_json`. |
| Experimental legacy report | Connected pipeline and re-coach | M2.1 emitted 1.6.0. The current legacy writer emits 1.7.0. It reads through its own report model. |

Public results have a top-level `provenance` object. Legacy reports use
`settings` and can carry profile-facing, opening-study and coaching fields.
M2.1's 1.6.0 and M2.2B's 1.1.0 belong to different envelopes.

Public 1.1.0 adds timelines, branch continuations, exercises and optional batch
behavior and tactics. For older 1.0.0 public results, missing arrays are empty
and optional batch fields are null. Reading older JSON does not invent missing
analysis. Reanalyze the original PGN to get a complete timeline and training
data. The older schema marker is retained when reading and reserializing.

Legacy 1.6.0 introduced the explicit mate winner for score distance zero.
Legacy 1.7.0 added before/after position and UCI continuation fields. Where
an older legacy result has an ambiguous zero-distance mate with no winner,
the schema cannot recover which side delivered it. Legacy JSON is not the
supported application integration format.

Consumers such as Knight Vision can use the package-root API, public result
types, `model_dump(mode="json")` and stable position keys. A game ID is scoped to
the submitted batch. Combine it with the ply for a move key, and keep your own
application game ID for persistence. See the [backend example](public-api.md).
