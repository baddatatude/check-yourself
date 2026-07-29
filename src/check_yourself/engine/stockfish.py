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
    ) -> None:
        self.path = path
        self.depth = depth
        self.multipv = multipv
        self.hash_mb = hash_mb
        self.threads = threads
        self.pv_moves = pv_moves
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
            self._engine = chess.engine.SimpleEngine.popen_uci(self.path)
        except (OSError, chess.engine.EngineError) as exc:
            raise EngineError(f"Failed to start Stockfish at {self.path!r}: {exc}") from exc
        try:
            self._engine.configure({"Hash": self.hash_mb, "Threads": self.threads})
        except chess.engine.EngineError:
            logger.debug("Stockfish rejected Hash/Threads configuration", exc_info=True)
        identity = self._engine.id
        name = identity.get("name", "Stockfish")
        ver = identity.get("version") or identity.get("author") or ""
        self._version = f"{name} {ver}".strip()
        logger.info("Started engine: %s", self._version)

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
            )
        except chess.engine.EngineError as exc:
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
        if self._engine is not None:
            try:
                self._engine.quit()
            except chess.engine.EngineError:
                logger.debug("Error quitting Stockfish", exc_info=True)
            self._engine = None


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
