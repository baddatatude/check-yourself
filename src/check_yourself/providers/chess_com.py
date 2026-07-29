"""Chess.com Published Data API client."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Protocol

import httpx

from check_yourself.config import AnalysisSettings, TimeControlFilter
from check_yourself.models import GameMetadata
from check_yourself.providers.pgn_utils import (
    classify_time_control,
    parse_pgn_metadata,
    user_color_for,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.chess.com/pub"
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{2,49}$")

# Re-export shared helpers for backward-compatible imports.
__all__ = [
    "API_BASE",
    "ChessComClient",
    "ChessComError",
    "HttpxChessComClient",
    "classify_time_control",
    "parse_pgn_metadata",
    "probe_chess_com",
    "user_color_for",
    "validate_username",
]


class ChessComError(Exception):
    """Chess.com API or parsing failure."""


class ChessComClient(Protocol):
    def fetch_recent_games(
        self,
        username: str,
        *,
        limit: int,
        time_control: TimeControlFilter | None = None,
    ) -> tuple[list[GameMetadata], list[str]]: ...

    def close(self) -> None: ...


def validate_username(username: str) -> str:
    name = username.strip()
    if not USERNAME_RE.fullmatch(name):
        raise ChessComError(
            f"Invalid Chess.com username: {username!r} "
            "(must start with a letter; letters, numbers, hyphen, underscore; 3–50 chars)"
        )
    return name


class HttpxChessComClient:
    """HTTP client for Chess.com public archives."""

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout: float = 30.0,
        retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        base_url: str = API_BASE,
    ) -> None:
        settings = AnalysisSettings()
        self.user_agent = user_agent or settings.chess_com_user_agent
        self.timeout = timeout
        self.retries = retries
        self.base_url = base_url.rstrip("/") + "/"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpxChessComClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _get_json(self, path: str) -> Any:
        # Relative paths (no leading slash) merge with base_url .../pub/
        rel = path.lstrip("/")
        last_err: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self._client.get(rel)
                if response.status_code == 404:
                    raise ChessComError(f"Chess.com resource not found: {path}")
                if response.status_code == 429:
                    if attempt < self.retries - 1:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    raise ChessComError(f"Chess.com rate limited for {path}")
                if response.status_code >= 400:
                    raise ChessComError(f"Chess.com HTTP {response.status_code} for {path}")
                return response.json()
            except httpx.HTTPError as exc:
                last_err = exc
                if attempt < self.retries - 1:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise ChessComError(f"Could not reach Chess.com: {exc}") from exc
        raise ChessComError(f"Chess.com request failed: {last_err}")

    def player_exists(self, username: str) -> bool:
        name = validate_username(username)
        try:
            self._get_json(f"/player/{name.lower()}")
            return True
        except ChessComError as exc:
            if "not found" in str(exc).lower():
                return False
            raise

    def list_archives(self, username: str) -> list[str]:
        name = validate_username(username)
        data = self._get_json(f"/player/{name.lower()}/games/archives")
        archives = list(data.get("archives") or [])
        return archives

    def fetch_archive_games(self, archive_url: str) -> list[dict[str, Any]]:
        # archive_url is absolute; convert to path under /pub/
        prefix = self.base_url.rstrip("/")
        if archive_url.startswith(prefix):
            path = archive_url[len(prefix) :].lstrip("/")
        elif archive_url.startswith("https://api.chess.com/pub/"):
            path = archive_url[len("https://api.chess.com/pub/") :]
        elif archive_url.startswith("https://api.chess.com/pub"):
            path = archive_url[len("https://api.chess.com/pub") :].lstrip("/")
        else:
            response = self._client.get(archive_url)
            if response.status_code == 404:
                raise ChessComError(f"Archive not found: {archive_url}")
            if response.status_code == 429:
                raise ChessComError(f"Rate limited fetching archive: {archive_url}")
            response.raise_for_status()
            return list(response.json().get("games") or [])
        data = self._get_json(path)
        return list(data.get("games") or [])

    def fetch_recent_games(
        self,
        username: str,
        *,
        limit: int,
        time_control: TimeControlFilter | None = None,
    ) -> tuple[list[GameMetadata], list[str]]:
        """Fetch the newest ``limit`` eligible games, oldest-first in the return list.

        Walks monthly archives from newest to oldest until enough games are collected,
        then returns exactly the newest N (when available), sorted chronologically.
        """
        if limit < 1:
            raise ChessComError("limit must be at least 1")

        name = validate_username(username)
        warnings: list[str] = []

        try:
            if not self.player_exists(name):
                raise ChessComError(f"Chess.com player not found: {name}")
        except ChessComError:
            raise

        try:
            archives = self.list_archives(name)
        except ChessComError as exc:
            raise ChessComError(f"Could not list archives for {name}: {exc}") from exc

        if not archives:
            warnings.append(f"No game archives found for {name}")
            return [], warnings

        # Newest archives last in API response; reverse to newest-first.
        archives_newest_first = list(reversed(archives))
        collected: list[GameMetadata] = []

        for archive_url in archives_newest_first:
            if len(collected) >= limit:
                break
            try:
                raw_games = self.fetch_archive_games(archive_url)
            except ChessComError as exc:
                warnings.append(f"Skipped archive {archive_url}: {exc}")
                logger.warning("Archive fetch failed: %s", exc)
                continue

            # Sort newest-first within the month (API order is not guaranteed).
            def _end_time(raw: dict[str, Any]) -> int:
                value = raw.get("end_time")
                return int(value) if isinstance(value, int) else 0

            for raw in sorted(raw_games, key=_end_time, reverse=True):
                if len(collected) >= limit:
                    break
                meta = self._raw_to_metadata(name, raw)
                if meta is None:
                    continue
                if time_control is not None and meta.time_class != time_control:
                    continue
                collected.append(meta)

        if len(collected) < limit:
            warnings.append(
                f"Requested {limit} games but only found {len(collected)} eligible games"
            )

        # collected is newest-first; keep the newest N (already capped), then chronological.
        newest = collected[:limit]
        newest.sort(key=lambda g: (g.end_time is None, g.end_time or 0, g.game_id))
        return newest, warnings

    def _raw_to_metadata(self, username: str, raw: dict[str, Any]) -> GameMetadata | None:
        pgn = (raw.get("pgn") or "").strip()
        if not pgn:
            return None
        try:
            return parse_pgn_metadata(
                pgn,
                username=username,
                url=raw.get("url"),
                end_time=raw.get("end_time"),
                time_control=raw.get("time_control"),
                time_class=raw.get("time_class"),
                rated=raw.get("rated"),
            )
        except Exception as exc:
            logger.warning("Malformed game skipped: %s", exc)
            return None


def probe_chess_com(user_agent: str | None = None, timeout: float = 10.0) -> tuple[bool, str]:
    """Check Chess.com API connectivity."""
    ua = user_agent or AnalysisSettings().chess_com_user_agent
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": ua}) as client:
            response = client.get(f"{API_BASE}/player/hikaru")
            if response.status_code == 200:
                return True, f"OK (HTTP {response.status_code})"
            return False, f"Unexpected HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        return False, f"Connection failed: {exc}"
