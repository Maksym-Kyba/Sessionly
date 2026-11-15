from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    database_url: str
    cors_allowed_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_cors_allowed_origins(cls, origins: list[str]) -> list[str]:
        normalized = [origin.strip().rstrip("/") for origin in origins]
        if not normalized or any(not origin or "*" in origin for origin in normalized):
            raise ValueError("CORS_ALLOWED_ORIGINS must contain explicit, non-wildcard origins")
        return normalized


settings = Settings()
