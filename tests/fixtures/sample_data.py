"""Sample PGNs and Chess.com API fixture payloads."""

SAMPLE_PGN_WHITE = """[Event "Live Chess"]
[Site "Chess.com"]
[Date "2024.01.15"]
[Round "-"]
[White "TestPlayer"]
[Black "OpponentOne"]
[Result "1-0"]
[ECO "C20"]
[Opening "King's Pawn Game"]
[TimeControl "600"]
[WhiteElo "1500"]
[BlackElo "1520"]
[Termination "TestPlayer won by resignation"]
[Link "https://www.chess.com/game/live/1001"]

1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7+ 1-0
"""

SAMPLE_PGN_BLACK = """[Event "Live Chess"]
[Site "Chess.com"]
[Date "2024.01.16"]
[Round "-"]
[White "OpponentTwo"]
[Black "TestPlayer"]
[Result "0-1"]
[ECO "B20"]
[Opening "Sicilian Defense"]
[TimeControl "180"]
[WhiteElo "1480"]
[BlackElo "1500"]
[Termination "TestPlayer won by checkmate"]
[Link "https://www.chess.com/game/live/1002"]

1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 0-1
"""

SAMPLE_PGN_RAPID = """[Event "Live Chess"]
[Site "Chess.com"]
[Date "2024.01.17"]
[White "TestPlayer"]
[Black "OpponentThree"]
[Result "1/2-1/2"]
[ECO "D00"]
[Opening "Queen's Pawn Game"]
[TimeControl "900+10"]
[Link "https://www.chess.com/game/live/1003"]

1. d4 d5 2. Bf4 Nf6 3. e3 e6 1/2-1/2
"""

ARCHIVES_RESPONSE = {
    "archives": [
        "https://api.chess.com/pub/player/testplayer/games/2024/01",
        "https://api.chess.com/pub/player/testplayer/games/2024/02",
    ]
}

PLAYER_RESPONSE = {
    "username": "TestPlayer",
    "player_id": 1,
    "url": "https://www.chess.com/member/TestPlayer",
}


def archive_games_jan() -> dict:
    return {
        "games": [
            {
                "url": "https://www.chess.com/game/live/1001",
                "pgn": SAMPLE_PGN_WHITE,
                "time_control": "600",
                "time_class": "rapid",
                "end_time": 1705300000,
                "rated": True,
                "white": {"username": "TestPlayer", "result": "win"},
                "black": {"username": "OpponentOne", "result": "lose"},
            },
            {
                "url": "https://www.chess.com/game/live/1000",
                "pgn": SAMPLE_PGN_BLACK.replace("1002", "1000").replace(
                    "2024.01.16", "2024.01.10"
                ),
                "time_control": "180",
                "time_class": "blitz",
                "end_time": 1705000000,
                "rated": True,
            },
        ]
    }


def archive_games_feb() -> dict:
    return {
        "games": [
            {
                "url": "https://www.chess.com/game/live/1003",
                "pgn": SAMPLE_PGN_RAPID,
                "time_control": "900+10",
                "time_class": "rapid",
                "end_time": 1708000000,
                "rated": True,
            },
            {
                "url": "https://www.chess.com/game/live/1002",
                "pgn": SAMPLE_PGN_BLACK,
                "time_control": "180",
                "time_class": "blitz",
                "end_time": 1707900000,
                "rated": True,
            },
        ]
    }
