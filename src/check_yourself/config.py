"""Configuration and analysis thresholds for Check Yourself."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

TimeControlFilter = Literal["bullet", "blitz", "rapid", "daily", "classical"]


class AnalysisSettings(BaseSettings):
    """Configurable Stockfish and classification settings."""

    model_config = SettingsConfigDict(
        env_prefix="CHECK_YOURSELF_",
        env_file=".env",
        extra="ignore",
    )

    stockfish_path: str | None = Field(
        default=None,
        description="Path to Stockfish binary; falls back to PATH lookup.",
    )
    depth: int = Field(default=12, ge=1, le=40)
    multipv: int = Field(default=1, ge=1, le=5)
    pv_moves: int = Field(default=6, ge=1, le=20, description="PV plies to store")
    hash_mb: int = Field(default=16, ge=1, le=1024)
    threads: int = Field(default=1, ge=1, le=32)
    workers: int = Field(
        default=1,
        ge=1,
        le=16,
        description="Parallel Stockfish processes for game analysis (1 = sequential).",
    )

    inaccuracy_threshold: int = Field(default=50, ge=1)
    mistake_threshold: int = Field(default=100, ge=1)
    blunder_threshold: int = Field(default=200, ge=1)
    # Legacy-style buckets used when classifying milder losses
    excellent_threshold: int = Field(default=10, ge=0)
    good_threshold: int = Field(default=25, ge=0)

    max_critical_positions: int = Field(default=5, ge=1, le=20)
    winning_cp: int = Field(default=200, ge=50, description="Clearly winning |eval| (cp)")
    equal_cp: int = Field(default=50, ge=10, description="Approximately equal |eval| (cp)")
    losing_cp: int = Field(default=200, ge=50, description="Clearly losing |eval| (cp)")

    chess_com_user_agent: str = Field(
        default="check-yourself/0.1 (+https://github.com/example/check-yourself; local analysis)",
    )
    chess_com_timeout: float = Field(default=30.0, ge=1.0)
    chess_com_retries: int = Field(default=3, ge=1, le=10)

    lichess_user_agent: str = Field(
        default="check-yourself/0.1 (+https://github.com/example/check-yourself; local analysis)",
    )
    lichess_timeout: float = Field(default=60.0, ge=1.0)
    lichess_retries: int = Field(default=3, ge=1, le=10)

    default_output_dir: Path = Field(default=Path("reports"))
    default_players_dir: Path = Field(
        default=Path("players"),
        description="Durable per-player coaching profiles directory.",
    )

    # Optional Stage 2 coaching (never written into report artifacts)
    openai_api_key: SecretStr | None = Field(
        default=None,
        description="OpenAI API key via CHECK_YOURSELF_OPENAI_API_KEY (or OPENAI_API_KEY).",
    )
    openai_model: str = Field(default="gpt-4.1-mini")
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    openai_timeout: float = Field(default=120.0, ge=5.0)
    coach_max_critical: int = Field(default=5, ge=1, le=20)
    coach_max_error_moves: int = Field(default=8, ge=1, le=40)
    coach_chunk_size: int = Field(default=5, ge=1, le=20)

    def resolve_stockfish_path(self) -> str | None:
        if self.stockfish_path:
            path = Path(self.stockfish_path).expanduser()
            if path.is_file():
                return str(path)
            return None
        return shutil.which("stockfish")

    def resolve_openai_api_key(self) -> str | None:
        """Resolve API key without logging or persisting it.

        Order: CHECK_YOURSELF_OPENAI_API_KEY (settings) → OPENAI_API_KEY env.
        """
        if self.openai_api_key is not None:
            value = self.openai_api_key.get_secret_value().strip()
            if value:
                return value
        env_key = os.environ.get("OPENAI_API_KEY", "").strip()
        return env_key or None


def classify_cp_loss(
    cp_loss: int,
    *,
    excellent: int = 10,
    good: int = 25,
    inaccuracy: int = 50,
    mistake: int = 100,
) -> str:
    """Classify evaluation loss into a transparent quality label."""
    if cp_loss <= 0:
        return "best"
    if cp_loss <= excellent:
        return "excellent"
    if cp_loss <= good:
        return "good"
    if cp_loss <= inaccuracy:
        return "inaccuracy"
    if cp_loss <= mistake:
        return "mistake"
    return "blunder"
