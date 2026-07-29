"""Data providers."""

from check_yourself.providers.base import (
    SUPPORTED_PLATFORMS,
    GameSource,
    PlatformName,
    ProviderError,
    create_game_source,
    normalize_platform,
)
from check_yourself.providers.chess_com import (
    ChessComClient,
    ChessComError,
    HttpxChessComClient,
    classify_time_control,
    parse_pgn_metadata,
    probe_chess_com,
    user_color_for,
    validate_username,
)
from check_yourself.providers.coaching import (
    CoachingError,
    CoachingProvider,
    OpenAICoachingProvider,
    build_game_coaching_payload,
    probe_openai_key,
)
from check_yourself.providers.lichess import (
    HttpxLichessClient,
    LichessError,
    probe_lichess,
    validate_lichess_username,
)

__all__ = [
    "SUPPORTED_PLATFORMS",
    "ChessComClient",
    "ChessComError",
    "CoachingError",
    "CoachingProvider",
    "GameSource",
    "HttpxChessComClient",
    "HttpxLichessClient",
    "LichessError",
    "OpenAICoachingProvider",
    "PlatformName",
    "ProviderError",
    "build_game_coaching_payload",
    "classify_time_control",
    "create_game_source",
    "normalize_platform",
    "parse_pgn_metadata",
    "probe_chess_com",
    "probe_lichess",
    "probe_openai_key",
    "user_color_for",
    "validate_lichess_username",
    "validate_username",
]
