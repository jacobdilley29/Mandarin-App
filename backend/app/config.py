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
    # Everything mutable lives under data_dir. In Docker this is the named
    # volume mounted at /data (set DATA_DIR=/data), so rebuilding the image
    # never touches it. Override with the DATA_DIR environment variable.
    data_dir: Path = REPO_ROOT / "data"

    # --- Backups (spec §7) ---
    # Rolling window of local backups. Daily cadence is driven by the cron job
    # in the backup container; backup_time is the schedule it renders.
    backup_retention_days: int = 30
    backup_time: str = "03:30"  # HH:MM, host local time

    # --- Frontend static files (built by Vite into frontend/dist) ---
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    @property
    def content_db_path(self) -> Path:
        """Curriculum + dictionary. Regenerable from content/*.json."""
        return self.data_dir / "content.db"

    @property
    def progress_db_path(self) -> Path:
        """Learner progress. Irreplaceable — this is what gets backed up."""
        return self.data_dir / "progress.db"

    @property
    def legacy_db_path(self) -> Path:
        """The pre-split single-file DB, migrated on first startup if present."""
        return self.data_dir / "mandarin.db"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def conversation_enabled(self) -> bool:
        """Talk tab is only available when an Anthropic key is configured."""
        return bool(self.anthropic_api_key)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
