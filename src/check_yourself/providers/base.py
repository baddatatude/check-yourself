"""Shared game-source protocol and platform factory."""

from __future__ import annotations

from typing import Literal, Protocol

from check_yourself.config import AnalysisSettings, TimeControlFilter
from check_yourself.models import GameMetadata

PlatformName = Literal["chess.com", "lichess"]

SUPPORTED_PLATFORMS: tuple[str, ...] = ("chess.com", "lichess")

_PLATFORM_ALIASES: dict[str, PlatformName] = {
    "chess.com": "chess.com",
    "chesscom": "chess.com",
    "chess_com": "chess.com",
    "lichess": "lichess",
    "lichess.org": "lichess",
}


class ProviderError(Exception):
    """Game-provider fetch or validation failure."""


class GameSource(Protocol):
    def fetch_recent_games(
        self,
        username: str,
        *,
        limit: int,
        time_control: TimeControlFilter | None = None,
    ) -> tuple[list[GameMetadata], list[str]]: ...

    def close(self) -> None: ...


def normalize_platform(value: str) -> PlatformName:
    """Normalize user input to a supported platform or raise ProviderError."""
    key = value.strip().lower()
    platform = _PLATFORM_ALIASES.get(key)
    if platform is None:
        supported = ", ".join(SUPPORTED_PLATFORMS)
        raise ProviderError(f"Unsupported platform: {value!r} (supported: {supported})")
    return platform


def create_game_source(
    platform: str,
    *,
    settings: AnalysisSettings | None = None,
) -> GameSource:
    """Build the HTTP game source for an explicit platform choice."""
    settings = settings or AnalysisSettings()
    name = normalize_platform(platform)
    if name == "chess.com":
        from check_yourself.providers.chess_com import HttpxChessComClient

        return HttpxChessComClient(
            user_agent=settings.chess_com_user_agent,
            timeout=settings.chess_com_timeout,
            retries=settings.chess_com_retries,
        )
    from check_yourself.providers.lichess import HttpxLichessClient

    return HttpxLichessClient(
        user_agent=settings.lichess_user_agent,
        timeout=settings.lichess_timeout,
        retries=settings.lichess_retries,
    )
