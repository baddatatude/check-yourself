"""Chess.com client unit tests with httpx mock transport."""

from __future__ import annotations

import httpx
import pytest
from tests.fixtures.sample_data import (
    ARCHIVES_RESPONSE,
    PLAYER_RESPONSE,
    SAMPLE_PGN_BLACK,
    SAMPLE_PGN_WHITE,
    archive_games_feb,
    archive_games_jan,
)

from check_yourself.providers.chess_com import (
    ChessComError,
    HttpxChessComClient,
    classify_time_control,
    parse_pgn_metadata,
    user_color_for,
    validate_username,
)


def test_validate_username() -> None:
    assert validate_username("cooperharris") == "cooperharris"
    with pytest.raises(ChessComError):
        validate_username("ab")
    with pytest.raises(ChessComError):
        validate_username("1bad")


def test_user_color_case_insensitive() -> None:
    assert user_color_for("TestPlayer", "testplayer", "Other") == "white"
    assert user_color_for("testplayer", "Other", "TESTPLAYER") == "black"
    assert user_color_for("nobody", "A", "B") is None


def test_classify_time_control() -> None:
    assert classify_time_control("60", "bullet") == "bullet"
    assert classify_time_control("180", None) == "blitz"
    assert classify_time_control("600", None) == "rapid"
    assert classify_time_control("1/86400", None) == "daily"
    assert classify_time_control(None, "correspondence") == "daily"


def test_parse_pgn_identifies_color() -> None:
    meta = parse_pgn_metadata(SAMPLE_PGN_WHITE, username="testplayer", end_time=1)
    assert meta is not None
    assert meta.user_color == "white"
    assert meta.eco == "C20"
    meta_b = parse_pgn_metadata(SAMPLE_PGN_BLACK, username="TestPlayer", end_time=2)
    assert meta_b is not None
    assert meta_b.user_color == "black"


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path.rstrip("/")
    if path.lower() == "/player/testplayer" or path.lower().endswith("/player/testplayer"):
        return httpx.Response(200, json=PLAYER_RESPONSE)
    if path.lower().endswith("/player/missinguser"):
        return httpx.Response(404, json={"message": "Not Found"})
    if path.lower().endswith("/player/testplayer/games/archives"):
        return httpx.Response(200, json=ARCHIVES_RESPONSE)
    if path.endswith("/2024/02"):
        return httpx.Response(200, json=archive_games_feb())
    if path.endswith("/2024/01"):
        return httpx.Response(200, json=archive_games_jan())
    if path.endswith("/2024/03"):
        return httpx.Response(500, text="boom")
    return httpx.Response(404, json={"message": "Not Found"})


def test_fetch_newest_n_across_archives() -> None:
    transport = httpx.MockTransport(_handler)
    with HttpxChessComClient(transport=transport, user_agent="check-yourself-test") as client:
        games, warnings = client.fetch_recent_games("TestPlayer", limit=3)
    assert len(games) == 3
    # Chronological order
    assert games[0].end_time is not None
    assert games[0].end_time <= games[1].end_time <= games[2].end_time
    # Newest three overall: 1003, 1002, 1001 by end_time
    ids = {g.game_id for g in games}
    assert ids == {"1001", "1002", "1003"}
    assert warnings == []


def test_time_control_filter_rapid() -> None:
    transport = httpx.MockTransport(_handler)
    with HttpxChessComClient(transport=transport, user_agent="check-yourself-test") as client:
        games, _ = client.fetch_recent_games("TestPlayer", limit=5, time_control="rapid")
    assert len(games) == 2
    assert all(g.time_class == "rapid" for g in games)


def test_fewer_than_requested_games() -> None:
    transport = httpx.MockTransport(_handler)
    with HttpxChessComClient(transport=transport, user_agent="check-yourself-test") as client:
        games, warnings = client.fetch_recent_games("TestPlayer", limit=10, time_control="rapid")
    assert len(games) == 2
    assert any("only found 2" in w for w in warnings)


def test_nonexistent_user() -> None:
    transport = httpx.MockTransport(_handler)
    with (
        HttpxChessComClient(transport=transport, user_agent="check-yourself-test") as client,
        pytest.raises(ChessComError, match="not found"),
    ):
        client.fetch_recent_games("MissingUser", limit=2)


def test_partial_archive_failure() -> None:
    archives = {
        "archives": [
            "https://api.chess.com/pub/player/testplayer/games/2024/01",
            "https://api.chess.com/pub/player/testplayer/games/2024/03",
            "https://api.chess.com/pub/player/testplayer/games/2024/02",
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path.lower().endswith("/player/testplayer"):
            return httpx.Response(200, json=PLAYER_RESPONSE)
        if path.lower().endswith("/archives"):
            return httpx.Response(200, json=archives)
        if path.endswith("/2024/03"):
            return httpx.Response(503, text="unavailable")
        if path.endswith("/2024/02"):
            # Only one game so the client continues into the failing archive
            feb = archive_games_feb()
            feb["games"] = feb["games"][:1]
            return httpx.Response(200, json=feb)
        if path.endswith("/2024/01"):
            return httpx.Response(200, json=archive_games_jan())
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with HttpxChessComClient(transport=transport, user_agent="check-yourself-test") as client:
        games, warnings = client.fetch_recent_games("TestPlayer", limit=3)
    assert len(games) == 3
    assert any("Skipped archive" in w or "503" in w or "HTTP" in w for w in warnings)
