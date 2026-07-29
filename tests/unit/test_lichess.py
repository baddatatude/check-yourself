"""Lichess client unit tests with httpx mock transport."""

from __future__ import annotations

import json

import httpx
import pytest
from tests.fixtures.sample_data import SAMPLE_PGN_BLACK, SAMPLE_PGN_WHITE

from check_yourself.providers.base import ProviderError, normalize_platform
from check_yourself.providers.lichess import (
    HttpxLichessClient,
    LichessError,
    validate_lichess_username,
)


def _lichess_pgn_white() -> str:
    return SAMPLE_PGN_WHITE.replace("Chess.com", "https://lichess.org").replace(
        "https://www.chess.com/game/live/1001",
        "https://lichess.org/abcd1234",
    )


def _lichess_pgn_black() -> str:
    return SAMPLE_PGN_BLACK.replace("Chess.com", "https://lichess.org").replace(
        "https://www.chess.com/game/live/1002",
        "https://lichess.org/efgh5678",
    )


def _ndjson_games() -> str:
    games = [
        {
            "id": "efgh5678",
            "rated": True,
            "speed": "blitz",
            "perf": "blitz",
            "createdAt": 1_705_400_000_000,
            "lastMoveAt": 1_705_400_100_000,
            "status": "mate",
            "players": {
                "white": {"user": {"name": "OpponentTwo"}, "rating": 1480},
                "black": {"user": {"name": "TestPlayer"}, "rating": 1500},
            },
            "winner": "black",
            "clock": {"initial": 180, "increment": 0},
            "opening": {"eco": "B20", "name": "Sicilian Defense"},
            "pgn": _lichess_pgn_black(),
        },
        {
            "id": "abcd1234",
            "rated": True,
            "speed": "rapid",
            "perf": "rapid",
            "createdAt": 1_705_300_000_000,
            "lastMoveAt": 1_705_300_050_000,
            "status": "resign",
            "players": {
                "white": {"user": {"name": "TestPlayer"}, "rating": 1500},
                "black": {"user": {"name": "OpponentOne"}, "rating": 1520},
            },
            "winner": "white",
            "clock": {"initial": 600, "increment": 0},
            "opening": {"eco": "C20", "name": "King's Pawn Game"},
            "pgn": _lichess_pgn_white(),
        },
    ]
    # Newest first as Lichess returns
    return "\n".join(json.dumps(g) for g in games) + "\n"


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path.rstrip("/")
    if path.lower() == "/api/user/testplayer":
        return httpx.Response(200, json={"id": "testplayer", "username": "TestPlayer"})
    if path.lower() == "/api/user/missinguser":
        return httpx.Response(404, json={"error": "Not found"})
    if path.lower() == "/api/games/user/testplayer":
        assert request.headers.get("Accept") == "application/x-ndjson"
        assert "perfType" in request.url.params
        return httpx.Response(
            200,
            text=_ndjson_games(),
            headers={"Content-Type": "application/x-ndjson"},
        )
    return httpx.Response(404, json={"error": "Not found"})


def test_validate_lichess_username() -> None:
    assert validate_lichess_username("DrNykterstein") == "DrNykterstein"
    with pytest.raises(LichessError):
        validate_lichess_username("a")


def test_normalize_platform() -> None:
    assert normalize_platform("chess.com") == "chess.com"
    assert normalize_platform("ChessCom") == "chess.com"
    assert normalize_platform("lichess") == "lichess"
    with pytest.raises(ProviderError, match="Unsupported platform"):
        normalize_platform("chess24")


def test_fetch_recent_games_lichess() -> None:
    transport = httpx.MockTransport(_handler)
    with HttpxLichessClient(transport=transport, user_agent="check-yourself-test") as client:
        games, warnings = client.fetch_recent_games("TestPlayer", limit=2)
    assert len(games) == 2
    assert games[0].game_id == "abcd1234"
    assert games[1].game_id == "efgh5678"
    assert games[0].user_color == "white"
    assert games[1].user_color == "black"
    assert games[0].time_class == "rapid"
    assert games[1].time_class == "blitz"
    assert games[0].end_time == 1_705_300_050
    assert not any("only found" in w for w in warnings)


def test_lichess_player_not_found() -> None:
    transport = httpx.MockTransport(_handler)
    with (
        HttpxLichessClient(transport=transport, user_agent="check-yourself-test") as client,
        pytest.raises(LichessError, match="not found"),
    ):
        client.fetch_recent_games("MissingUser", limit=1)


def test_lichess_time_control_filter_maps_daily() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path.rstrip("/")
        if path.lower() == "/api/user/testplayer":
            return httpx.Response(200, json={"id": "testplayer"})
        if path.lower() == "/api/games/user/testplayer":
            seen["perfType"] = request.url.params.get("perfType", "")
            return httpx.Response(200, text="", headers={"Content-Type": "application/x-ndjson"})
        return httpx.Response(404)

    with HttpxLichessClient(
        transport=httpx.MockTransport(handler),
        user_agent="check-yourself-test",
    ) as client:
        games, warnings = client.fetch_recent_games("TestPlayer", limit=3, time_control="daily")
    assert seen["perfType"] == "correspondence"
    assert games == []
    assert any("only found 0" in w for w in warnings)
