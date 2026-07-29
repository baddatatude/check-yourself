"""Shared PGN parsing helpers for game providers."""

from __future__ import annotations

import logging
from io import StringIO

import chess.pgn

from check_yourself.models import GameMetadata, PlayerColor, TimeClass

logger = logging.getLogger(__name__)


def classify_time_control(
    time_control: str | None,
    time_class: str | None = None,
) -> TimeClass:
    """Map provider time_class / time_control into a coarse filter bucket."""
    if time_class:
        tc = time_class.lower().strip()
        if tc == "correspondence":
            return "daily"
        if tc in {"bullet", "blitz", "rapid", "daily", "classical"}:
            return tc  # type: ignore[return-value]
    if not time_control:
        return "unknown"
    raw = time_control.strip().lower()
    if raw in {"-", "0", "none"}:
        return "daily"
    # Formats like "600" or "600+5" or "1/86400"
    if "/" in raw:
        return "daily"
    try:
        base = raw.split("+", 1)[0]
        seconds = int(float(base))
    except ValueError:
        return "unknown"
    if seconds < 180:
        return "bullet"
    if seconds < 600:
        return "blitz"
    if seconds < 1800:
        return "rapid"
    return "classical"


def user_color_for(username: str, white: str, black: str) -> PlayerColor | None:
    u = username.lower()
    if white.lower() == u:
        return "white"
    if black.lower() == u:
        return "black"
    return None


def game_id_from(url: str | None, end_time: int | None, fallback: str) -> str:
    if url:
        slug = url.rstrip("/").split("/")[-1]
        if slug:
            return slug
    if end_time is not None:
        return str(end_time)
    return fallback


def parse_pgn_metadata(
    pgn_text: str,
    *,
    username: str,
    url: str | None = None,
    end_time: int | None = None,
    time_control: str | None = None,
    time_class: str | None = None,
    rated: bool | None = None,
    game_id: str | None = None,
) -> GameMetadata | None:
    """Parse a PGN string into GameMetadata; return None if unusable."""
    try:
        game = chess.pgn.read_game(StringIO(pgn_text))
    except Exception as exc:
        logger.warning("Failed to parse PGN: %s", exc)
        return None
    if game is None:
        return None

    headers = game.headers
    white = headers.get("White", "?")
    black = headers.get("Black", "?")
    color = user_color_for(username, white, black)
    if color is None:
        logger.warning(
            "Username %s not found in PGN players (%s vs %s); skipping",
            username,
            white,
            black,
        )
        return None

    tc = time_control or headers.get("TimeControl")
    tcl = classify_time_control(tc, time_class)
    gid = game_id or game_id_from(
        url or headers.get("Link") or headers.get("Site"),
        end_time,
        "unknown",
    )

    return GameMetadata(
        game_id=gid,
        url=url or headers.get("Link"),
        end_time=end_time,
        white=white,
        black=black,
        result=headers.get("Result", "*"),
        user_color=color,
        time_control=tc,
        time_class=tcl,
        rated=rated,
        opening=headers.get("Opening"),
        eco=headers.get("ECO"),
        event=headers.get("Event"),
        site=headers.get("Site"),
        date=headers.get("Date"),
        white_elo=headers.get("WhiteElo"),
        black_elo=headers.get("BlackElo"),
        termination=headers.get("Termination"),
        pgn=pgn_text.strip(),
    )
