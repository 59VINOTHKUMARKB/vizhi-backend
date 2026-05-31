"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration consumed across the entire backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./vizhi.db"

    # ── Provider API Keys ───────────────────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    qwen_api_key: str = ""

    # ── Self-hosted endpoints ───────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"

    # ── CORS ────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://192.168.0.9:3000"

    # ── API Key Generation ──────────────────────────────────────────────
    api_key_prefix: str = "vz_live_"

    # ── Helpers ─────────────────────────────────────────────────────────
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# Singleton – import ``settings`` everywhere.
settings = Settings()
