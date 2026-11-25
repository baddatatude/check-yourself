"""Stockfish UCI engine adapter."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Protocol

import chess
import chess.engine

from check_yourself.config import AnalysisSettings
from check_yourself.engine.evaluation import WhiteEval, parse_score_white

logger = logging.getLogger(__name__)


class EngineError(Exception):
    """Stockfish / UCI failure."""


@dataclass(frozen=True)
class EngineAnalysis:
    fen: str
    white_eval: WhiteEval
    best_move: chess.Move | None
    pv: list[chess.Move]
    depth: int


class EngineAdapter(Protocol):
    def analyse(self, board: chess.Board, *, depth: int | None = None) -> EngineAnalysis: ...

    def version(self) -> str: ...

    def close(self) -> None: ...


class StockfishEngine(AbstractContextManager["StockfishEngine"]):
    """Thin wrapper around python-chess SimpleEngine."""

    def __init__(
        self,
        path: str,
        *,
        depth: int = 12,
        multipv: int = 1,
        hash_mb: int = 16,
        threads: int = 1,
        pv_moves: int = 6,
        timeout: float = 10,
        strict_configuration: bool = False,
    ) -> None:
        self.path = path
        self.depth = depth
        self.multipv = multipv
        self.hash_mb = hash_mb
        self.threads = threads
        self.pv_moves = pv_moves
        self.timeout = timeout
        self.strict_configuration = strict_configuration
        self._game: object | None = None
        self._engine: chess.engine.SimpleEngine | None = None
        self._version = "unknown"

    @classmethod
    def from_settings(cls, settings: AnalysisSettings) -> StockfishEngine:
        path = settings.resolve_stockfish_path()
        if not path:
            raise EngineError(
                "Stockfish binary not found. Install Stockfish and ensure it is on PATH, "
                "or pass --stockfish-path."
            )
        return cls(
            path,
            depth=settings.depth,
            multipv=settings.multipv,
            hash_mb=settings.hash_mb,
            threads=settings.threads,
            pv_moves=settings.pv_moves,
        )

    def __enter__(self) -> StockfishEngine:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def open(self) -> None:
        if self._engine is not None:
            return
        try:
            engine = chess.engine.SimpleEngine.popen_uci(self.path, timeout=self.timeout)
        except (OSError, chess.engine.EngineError) as exc:
            raise EngineError(f"Failed to start Stockfish at {self.path!r}: {exc}") from exc
        self._engine = engine
        configured = False
        try:
            try:
                engine.configure({"Hash": self.hash_mb, "Threads": self.threads})
            except chess.engine.EngineError:
                if self.strict_configuration:
                    raise
                logger.debug("Stockfish rejected Hash/Threads configuration", exc_info=True)
            identity = engine.id
            self._version = identity.get("name", "unknown")
            version = identity.get("version")
            if version:
                self._version += f" {version}"
            configured = True
        except (OSError, chess.engine.EngineError) as exc:
            raise EngineError(f"Could not configure Stockfish at {self.path!r}: {exc}") from exc
        finally:
            if not configured:
                self.close()
        logger.info("Started engine: %s", self._version)

    def start_game(self) -> None:
        """Reset the UCI game context before analyzing another game."""
        self._game = object()

    def version(self) -> str:
        if self._engine is None:
            self.open()
        return self._version

    def analyse(self, board: chess.Board, *, depth: int | None = None) -> EngineAnalysis:
        if self._engine is None:
            self.open()
        assert self._engine is not None
        limit_depth = depth if depth is not None else self.depth
        try:
            info = self._engine.analyse(
                board,
                chess.engine.Limit(depth=limit_depth),
                multipv=self.multipv,
                game=self._game,
            )
        except TimeoutError as exc:
            raise EngineError(f"Stockfish search exceeded {self.timeout:g} seconds") from exc
        except (OSError, chess.engine.EngineError) as exc:
            raise EngineError(f"Stockfish analysis failed: {exc}") from exc

        primary = info[0] if isinstance(info, Sequence) and not isinstance(info, dict) else info

        score = primary.get("score")
        if score is None:
            raise EngineError("Stockfish returned no score")
        white_eval = parse_score_white(score)
        pv = list(primary.get("pv") or [])
        best = pv[0] if pv else None
        return EngineAnalysis(
            fen=board.fen(),
            white_eval=white_eval,
            best_move=best,
            pv=pv[: self.pv_moves],
            depth=int(primary.get("depth") or limit_depth),
        )

    def close(self) -> None:
        engine, self._engine = self._engine, None
        if engine is None:
            return
        try:
            engine.quit()
        except (OSError, chess.engine.EngineError):
            logger.debug("Error quitting Stockfish", exc_info=True)
        finally:
            # python-chess closes the subprocess transport even if UCI quit fails.
            engine.close()
            try:
                engine.returncode.result(timeout=self.timeout)
            except TimeoutError:
                logger.warning("Timed out waiting for the Stockfish transport to close")


def probe_stockfish(path: str | None) -> tuple[bool, str]:
    """Return (ok, message) without leaving a long-lived engine process."""
    resolved = path or AnalysisSettings().resolve_stockfish_path()
    if not resolved:
        return False, "Stockfish not found on PATH and no --stockfish-path provided"
    if not Path(resolved).is_file() and path:
        return False, f"Stockfish path does not exist: {resolved}"
    try:
        with StockfishEngine(resolved, depth=1, hash_mb=16, threads=1) as engine:
            version = engine.version()
            board = chess.Board()
            engine.analyse(board, depth=1)
            return True, version
    except EngineError as exc:
        return False, str(exc)
