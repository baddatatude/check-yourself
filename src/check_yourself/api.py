"""Offline PGN analysis. The top-level package re-exports the public API."""

from __future__ import annotations

import shutil
from io import StringIO
from pathlib import Path
from typing import Literal

import chess
import chess.pgn
from pydantic import BaseModel, ConfigDict, Field

from check_yourself import __version__
from check_yourself.analysis.aggregate import aggregate_stats
from check_yourself.analysis.behavior import summarize_behavior
from check_yourself.analysis.game_analyzer import GameAnalyzer
from check_yourself.analysis.tactics_analyzer import analyze_piece_and_tactics
from check_yourself.config import AnalysisSettings
from check_yourself.engine.stockfish import EngineError, StockfishEngine
from check_yourself.models import (
    BehaviorSummary,
    GameAnalysisResult,
    GameMetadata,
    OverallStats,
    PlayerColor,
    TacticsReport,
)


class AnalysisError(Exception):
    """Base exception for PGN analysis failures."""


class PGNError(AnalysisError):
    """The collection, game, or requested perspective could not be analyzed."""


class StockfishError(AnalysisError):
    """The local Stockfish executable could not be started, configured or queried."""


class AnalysisOptions(BaseModel):
    """Explicit options for one local Stockfish process."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    stockfish_path: Path | None = None
    depth: int = Field(default=12, ge=1, le=40)
    threads: int = Field(default=1, ge=1, le=32)
    hash_mb: int = Field(default=16, ge=1, le=1024)
    pv_moves: int = Field(default=6, ge=1, le=20)
    max_critical_positions: int = Field(default=5, ge=1, le=20)
    timeout: float = Field(default=30, gt=0, allow_inf_nan=False)


class AnalysisProvenance(BaseModel):
    package_version: str
    stockfish_version: str
    depth: int
    multipv: Literal[1] = 1
    threads: int
    hash_mb: int
    pv_moves: int
    max_critical_positions: int
    timeout: float


class AnalysisResult(BaseModel):
    """Versioned results for one or more games in input order."""

    schema_version: Literal["1.0.0", "1.1.0"] = "1.1.0"
    provenance: AnalysisProvenance
    player: str | None = None
    games: list[GameAnalysisResult] = Field(min_length=1)
    overall: OverallStats
    behavior: BehaviorSummary | None = None
    tactics: TacticsReport | None = None


class _GameBuilder(chess.pgn.GameBuilder[chess.pgn.Game]):
    def handle_error(self, error: Exception) -> None:
        self.game.errors.append(error)

    def visit_result(self, result: str) -> None:
        header = self.game.headers["Result"]
        if header not in {"*", result}:
            self.handle_error(ValueError("Result header disagrees with the movetext"))
        super().visit_result(result)


def _parse_games(
    pgn: str, color: PlayerColor | None, player: str | None, *, single: bool
) -> list[tuple[chess.pgn.Game, GameMetadata]]:
    if color is not None and color not in ("white", "black"):
        raise PGNError("Color must be white or black")
    if player is not None and (color is not None or not player.strip()):
        raise PGNError("Choose a nonempty player name or a fixed color")

    text = pgn.removeprefix("\ufeff")
    stream = StringIO(text)
    games: list[tuple[chess.pgn.Game, GameMetadata]] = []
    while True:
        start = stream.tell()
        index = len(games) + 1
        try:
            game = chess.pgn.read_game(stream, Visitor=_GameBuilder)
        except (ValueError, OverflowError) as exc:
            raise PGNError(f"Game {index}: could not parse PGN") from exc
        if game is None:
            break
        if single and games:
            raise PGNError("Expected one PGN game. Use analyze_games for a collection.")
        if game.errors:
            raise PGNError(f"Game {index}: {game.errors[0]}")
        try:
            board = game.board()
        except ValueError as exc:
            raise PGNError(f"Game {index}: {exc}") from exc
        if type(board) is not chess.Board or board.chess960:
            raise PGNError(f"Game {index}: only standard chess is supported")
        if not board.is_valid():
            raise PGNError(f"Game {index}: invalid starting position")
        if not game.variations:
            raise PGNError(f"Game {index}: no moves found")

        headers = game.headers
        white, black = headers["White"], headers["Black"]
        selected: PlayerColor = color or "white"
        if player is not None:
            needle = player.strip().casefold()
            matches_white = white.strip().casefold() == needle
            matches_black = black.strip().casefold() == needle
            if matches_white == matches_black:
                qualifier = "matches both sides" if matches_white else "was not found"
                raise PGNError(f"Game {index}: player {player.strip()!r} {qualifier}")
            selected = "white" if matches_white else "black"

        result = headers["Result"]
        if result not in {"*", "1-0", "0-1", "1/2-1/2"}:
            raise PGNError(f"Game {index}: invalid PGN result {result!r}")
        games.append((
            game,
            GameMetadata(
                game_id=f"game-{index}",
                white=white,
                black=black,
                user_color=selected,
                result=result,
                time_control=headers.get("TimeControl"),
                opening=headers.get("Opening"),
                eco=headers.get("ECO"),
                event=headers.get("Event"),
                date=headers.get("Date"),
                pgn=text[start:stream.tell()].strip(),
            ),
        ))
    if not games:
        raise PGNError("No games found in the PGN")
    return games


def _analyze(
    pgn: str,
    *,
    options: AnalysisOptions | None,
    color: PlayerColor | None,
    player: str | None,
    single: bool,
) -> AnalysisResult:
    inputs = _parse_games(pgn, color, player, single=single)
    options = options or AnalysisOptions()
    executable = (
        str(options.stockfish_path.expanduser().absolute())
        if options.stockfish_path is not None
        else shutil.which("stockfish")
    )
    if executable is None:
        raise StockfishError("Stockfish was not found on PATH. Set AnalysisOptions.stockfish_path.")

    # Public options are validated above. Construct internal defaults without reading .env or env.
    settings = AnalysisSettings.model_construct(
        depth=options.depth, threads=options.threads, hash_mb=options.hash_mb,
        pv_moves=options.pv_moves, max_critical_positions=options.max_critical_positions,
    )
    try:
        with StockfishEngine(
            executable, depth=options.depth, threads=options.threads,
            hash_mb=options.hash_mb, pv_moves=options.pv_moves, timeout=options.timeout,
            strict_configuration=True,
        ) as engine:
            version = engine.version()
            analyzer = GameAnalyzer(engine, settings)
            games = []
            for game, metadata in inputs:
                engine.start_game()
                try:
                    games.append(analyzer._analyze_game(game, metadata))
                except EngineError as exc:
                    raise StockfishError(f"{metadata.game_id}: {exc}") from exc
    except EngineError as exc:
        raise StockfishError(str(exc)) from exc

    return AnalysisResult(
        provenance=AnalysisProvenance(
            package_version=__version__,
            stockfish_version=version,
            depth=options.depth,
            threads=options.threads,
            hash_mb=options.hash_mb,
            pv_moves=options.pv_moves,
            max_critical_positions=options.max_critical_positions,
            timeout=options.timeout,
        ),
        player=player.strip() if player is not None else None,
        games=games,
        overall=aggregate_stats(games, settings),
        behavior=summarize_behavior(games, advantage_threshold_cp=settings.winning_cp)
        if len(games) > 1 else None,
        tactics=analyze_piece_and_tactics(games) if len(games) > 1 else None,
    )


def analyze_game(
    pgn: str, *, options: AnalysisOptions | None = None,
    color: PlayerColor | None = None, player: str | None = None,
) -> AnalysisResult:
    """Analyze exactly one PGN game. White is the default perspective."""
    return _analyze(pgn, options=options, color=color, player=player, single=True)


def analyze_games(
    pgn: str, *, options: AnalysisOptions | None = None,
    color: PlayerColor | None = None, player: str | None = None,
) -> AnalysisResult:
    """Analyze a PGN collection sequentially. White is the default perspective."""
    return _analyze(pgn, options=options, color=color, player=player, single=False)
