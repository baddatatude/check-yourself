"""Lichess public API client."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from check_yourself.config import AnalysisSettings, TimeControlFilter
from check_yourself.models import GameMetadata
from check_yourself.providers.pgn_utils import parse_pgn_metadata

logger = logging.getLogger(__name__)

API_BASE = "https://lichess.org"
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,29}$")
STANDARD_PERF_TYPES = "bullet,blitz,rapid,classical,correspondence"


class LichessError(Exception):
    """Lichess API or parsing failure."""


def validate_lichess_username(username: str) -> str:
    name = username.strip()
    if not USERNAME_RE.fullmatch(name):
        raise LichessError(
            f"Invalid Lichess username: {username!r} "
            "(letters, numbers, hyphen, underscore; 2–30 chars)"
        )
    return name


def _time_control_to_perf_type(time_control: TimeControlFilter | None) -> str:
    if time_control is None:
        return STANDARD_PERF_TYPES
    if time_control == "daily":
        return "correspondence"
    return time_control


def _ms_to_end_time(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        # Lichess timestamps are milliseconds.
        return int(value // 1000)
    return None


def _clock_to_time_control(clock: dict[str, Any] | None) -> str | None:
    if not clock:
        return None
    initial = clock.get("initial")
    increment = clock.get("increment")
    if not isinstance(initial, int):
        return None
    if isinstance(increment, int) and increment > 0:
        return f"{initial}+{increment}"
    return str(initial)


class HttpxLichessClient:
    """HTTP client for Lichess public game export."""

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        timeout: float = 60.0,
        retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        base_url: str = API_BASE,
    ) -> None:
        settings = AnalysisSettings()
        self.user_agent = user_agent or settings.lichess_user_agent
        self.timeout = timeout
        self.retries = retries
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url + "/",
            headers={"User-Agent": self.user_agent},
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpxLichessClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        rel = path.lstrip("/")
        last_err: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self._client.request(method, rel, params=params, headers=headers)
                if response.status_code == 404:
                    raise LichessError(f"Lichess resource not found: {path}")
                if response.status_code == 429:
                    if attempt < self.retries - 1:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    raise LichessError(f"Lichess rate limited for {path}")
                if response.status_code >= 400:
                    raise LichessError(f"Lichess HTTP {response.status_code} for {path}")
                return response
            except httpx.HTTPError as exc:
                last_err = exc
                if attempt < self.retries - 1:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise LichessError(f"Could not reach Lichess: {exc}") from exc
        raise LichessError(f"Lichess request failed: {last_err}")

    def player_exists(self, username: str) -> bool:
        name = validate_lichess_username(username)
        try:
            self._request("GET", f"/api/user/{name}")
            return True
        except LichessError as exc:
            if "not found" in str(exc).lower():
                return False
            raise

    def fetch_recent_games(
        self,
        username: str,
        *,
        limit: int,
        time_control: TimeControlFilter | None = None,
    ) -> tuple[list[GameMetadata], list[str]]:
        """Fetch the newest ``limit`` standard games, oldest-first in the return list."""
        if limit < 1:
            raise LichessError("limit must be at least 1")

        name = validate_lichess_username(username)
        warnings: list[str] = []

        if not self.player_exists(name):
            raise LichessError(f"Lichess player not found: {name}")

        params = {
            "max": limit,
            "perfType": _time_control_to_perf_type(time_control),
            "pgnInJson": "true",
            "opening": "true",
            "clocks": "true",
            "finished": "true",
            "ongoing": "false",
            "sort": "dateDesc",
            "moves": "true",
            "tags": "true",
        }
        response = self._request(
            "GET",
            f"/api/games/user/{name}",
            params=params,
            headers={"Accept": "application/x-ndjson"},
        )

        collected: list[GameMetadata] = []
        for line in response.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.append(f"Skipped malformed Lichess NDJSON line: {exc}")
                continue
            if not isinstance(raw, dict):
                continue
            meta = self._raw_to_metadata(name, raw)
            if meta is None:
                continue
            if time_control is not None and meta.time_class != time_control:
                continue
            collected.append(meta)
            if len(collected) >= limit:
                break

        if len(collected) < limit:
            warnings.append(
                f"Requested {limit} games but only found {len(collected)} eligible games"
            )

        # API returns newest-first; return chronological for analysis.
        collected.sort(key=lambda g: (g.end_time is None, g.end_time or 0, g.game_id))
        return collected, warnings

    def _raw_to_metadata(self, username: str, raw: dict[str, Any]) -> GameMetadata | None:
        pgn = (raw.get("pgn") or "").strip()
        if not pgn:
            return None

        game_id = str(raw.get("id") or "").strip() or None
        url = f"https://lichess.org/{game_id}" if game_id else None
        end_time = _ms_to_end_time(raw.get("lastMoveAt") or raw.get("createdAt"))
        speed = raw.get("speed")
        time_class = str(speed) if isinstance(speed, str) else None
        clock = raw.get("clock") if isinstance(raw.get("clock"), dict) else None
        time_control = _clock_to_time_control(clock)
        rated = raw.get("rated") if isinstance(raw.get("rated"), bool) else None

        # Prefer opening name from JSON when present.
        opening_name: str | None = None
        opening = raw.get("opening")
        if isinstance(opening, dict):
            name = opening.get("name")
            if isinstance(name, str) and name.strip():
                opening_name = name.strip()

        try:
            meta = parse_pgn_metadata(
                pgn,
                username=username,
                url=url,
                end_time=end_time,
                time_control=time_control,
                time_class=time_class,
                rated=rated,
                game_id=game_id,
            )
        except Exception as exc:
            logger.warning("Malformed Lichess game skipped: %s", exc)
            return None
        if meta is None:
            return None
        if opening_name and not meta.opening:
            return meta.model_copy(update={"opening": opening_name})
        return meta


def probe_lichess(user_agent: str | None = None, timeout: float = 10.0) -> tuple[bool, str]:
    """Check Lichess API connectivity."""
    ua = user_agent or AnalysisSettings().lichess_user_agent
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": ua}) as client:
            response = client.get(f"{API_BASE}/api/user/lichess")
            if response.status_code == 200:
                return True, f"OK (HTTP {response.status_code})"
            return False, f"Unexpected HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        return False, f"Connection failed: {exc}"
