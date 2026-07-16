"""Application configuration, loaded from environment / .env.

All settings have safe defaults so the skeleton runs with no .env present.
The Anthropic key is optional — the app must degrade gracefully when it is
absent (the Talk tab is disabled; everything else works).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = two levels up from this file (backend/app/config.py -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Look for a .env at the repo root; ignore unknown keys so future phases
    # can add vars without breaking Phase 0.
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Networking ---
    host: str = "0.0.0.0"
    # Default 3002 per the current run request; spec's canonical default is 3170.
    port: int = 3002

    # --- Optional integrations ---
    anthropic_api_key: str | None = None
    whisper_model: str = "small"

    # --- Storage ---
    # Single SQLite file + audio cache live under data/ for easy backup.
    data_dir: Path = REPO_ROOT / "data"

    # --- Frontend static files (built by Vite into frontend/dist) ---
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mandarin.db"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def conversation_enabled(self) -> bool:
        """Talk tab is only available when an Anthropic key is configured."""
        return bool(self.anthropic_api_key)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
