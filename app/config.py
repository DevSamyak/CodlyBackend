from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment variables are prefixed with CPT_ (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CPT_", extra="ignore")

    clist_username: str = ""  # clist.by credentials — only needed for TopCoder
    clist_api_key: str = ""
    cors_origins: List[str] = ["*"]
    http_timeout_seconds: float = 20.0
    profile_ttl_seconds: int = 300
    history_ttl_seconds: int = 600
    contests_ttl_seconds: int = 600
    potd_ttl_seconds: int = 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
