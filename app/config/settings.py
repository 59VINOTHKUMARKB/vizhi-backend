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
    #---- Remote Data base url ___________
   
    remote_database_url:str = ""

    #----- Sync settings for the local to the server -----

    sync_enabled: bool = True
    sync_interval:int = 30
    sync_batch_size: int = 100

    

    # ── Inference routing ───────────────────────────────────────────────
    inference_backend: str = "huggingface"
    inference_model_map: str = ""
    hf_token: str = ""
    huggingface_api_key: str = ""
    huggingface_base_url: str = "https://router.huggingface.co/v1"
    custom_inference_api_key: str = ""
    custom_inference_base_url: str = ""

    # ── Legacy provider API keys ────────────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    qwen_api_key: str = ""

    # ── Self-hosted endpoints ───────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"

    # ── CORS ────────────────────────────────────────────────────────────
    cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001,"
        "http://localhost:3002,http://127.0.0.1:3002,"
        "http://192.168.0.9:3000"
    )

    # ── API Key Generation ──────────────────────────────────────────────
    api_key_prefix: str = "vz_live_"

    # ── Frontend user authentication ────────────────────────────────────
    auth_jwt_secret: str = "change-me-in-production"
    auth_jwt_issuer: str = "vizhi"
    auth_token_ttl_minutes: int = 60 * 24 * 7
    auth_cookie_name: str = "vizhi_session"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    google_client_id: str = ""

    # ── Helpers ─────────────────────────────────────────────────────────
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# Singleton – import ``settings`` everywhere.
settings = Settings()
