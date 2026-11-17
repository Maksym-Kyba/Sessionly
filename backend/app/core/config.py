from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_env: Literal["development", "production"] = "development"
    database_url: str
    test_database_url: str | None = None
    cors_allowed_origins: list[str] = ["http://localhost:3000"]
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    frontend_auth_success_url: str | None = None
    frontend_auth_error_url: str | None = None
    frontend_auth_redirect_allowlist: list[str] = ["http://localhost:3000/"]
    oauth_state_encryption_key: str | None = None
    csrf_secret_key: str | None = None
    session_cookie_name: str = "__Host-sessionly_session"
    oauth_browser_cookie_name: str = "__Host-sessionly_oauth"
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    default_psychologist_time_zone: str = "Europe/Kyiv"
    session_ttl_seconds: int = 7 * 24 * 60 * 60
    client_verification_secret_key: str = "local-development-only-change-me-32"
    client_verification_link_base_url: str = "http://localhost:3000/verify-email"
    client_verification_ttl_seconds: int = 30 * 60
    client_booking_token_ttl_seconds: int = 90 * 24 * 60 * 60
    client_verification_email_limit_per_hour: int = 3
    client_verification_psychologist_limit_per_hour: int = 100
    client_verification_consume_limit_per_minute: int = 300

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

    @field_validator("frontend_auth_redirect_allowlist")
    @classmethod
    def validate_redirect_allowlist(cls, urls: list[str]) -> list[str]:
        normalized = [url.strip() for url in urls]
        if not normalized:
            raise ValueError("Frontend redirect allowlist must not be empty")
        for url in normalized:
            parsed = urlsplit(url)
            local_http = parsed.scheme == "http" and parsed.hostname == "localhost"
            if (
                (parsed.scheme != "https" and not local_http)
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.fragment
            ):
                raise ValueError("Frontend redirects must use HTTPS or localhost without fragments")
        return normalized

    @model_validator(mode="after")
    def validate_cookie_policy(self) -> "Settings":
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SameSite=None cookies require SESSION_COOKIE_SECURE=true")
        if not self.session_cookie_secure and self.session_cookie_name.startswith("__Host-"):
            raise ValueError("__Host- session cookies require SESSION_COOKIE_SECURE=true")
        if not self.session_cookie_secure and self.oauth_browser_cookie_name.startswith("__Host-"):
            raise ValueError("__Host- OAuth cookies require SESSION_COOKIE_SECURE=true")
        if self.session_ttl_seconds != 7 * 24 * 60 * 60:
            raise ValueError("Psychologist sessions must expire after seven days")
        if self.csrf_secret_key and len(self.csrf_secret_key) < 32:
            raise ValueError("CSRF_SECRET_KEY must contain at least 32 characters")
        if len(self.client_verification_secret_key) < 32:
            raise ValueError("CLIENT_VERIFICATION_SECRET_KEY must contain at least 32 characters")
        verification_url = urlsplit(self.client_verification_link_base_url)
        local_verification_url = (
            verification_url.scheme == "http" and verification_url.hostname == "localhost"
        )
        if (
            (verification_url.scheme != "https" and not local_verification_url)
            or not verification_url.hostname
            or verification_url.query
            or verification_url.fragment
            or verification_url.username is not None
            or verification_url.password is not None
        ):
            raise ValueError("Client verification links must use HTTPS or localhost without query")
        if self.client_verification_ttl_seconds != 30 * 60:
            raise ValueError("Client verification links must expire after 30 minutes")
        if self.client_booking_token_ttl_seconds < 60 * 60:
            raise ValueError("Client booking tokens must last at least one hour")
        for url in (self.frontend_auth_success_url, self.frontend_auth_error_url):
            if url is not None and url not in self.frontend_auth_redirect_allowlist:
                raise ValueError("Configured frontend auth redirects must be in the allowlist")
        try:
            ZoneInfo(self.default_psychologist_time_zone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                "DEFAULT_PSYCHOLOGIST_TIME_ZONE must be a valid IANA time zone"
            ) from exc
        if self.app_env == "production":
            if self.client_verification_secret_key == "local-development-only-change-me-32":
                raise ValueError("Production requires a unique CLIENT_VERIFICATION_SECRET_KEY")
            if verification_url.scheme != "https":
                raise ValueError("Production verification links must use HTTPS")
            if not self.session_cookie_secure:
                raise ValueError("Production session cookies must set SESSION_COOKIE_SECURE=true")
            if self.google_redirect_uri and urlsplit(self.google_redirect_uri).scheme != "https":
                raise ValueError("Production GOOGLE_REDIRECT_URI must use HTTPS")
            if any(urlsplit(origin).scheme != "https" for origin in self.cors_allowed_origins):
                raise ValueError("Production CORS origins must use HTTPS")
            if any(
                url is not None and urlsplit(url).scheme != "https"
                for url in (self.frontend_auth_success_url, self.frontend_auth_error_url)
            ):
                raise ValueError("Production frontend auth redirects must use HTTPS")
        return self

    @property
    def session_cookie_path(self) -> str:
        return "/" if self.session_cookie_name.startswith("__Host-") else "/api/v1"

    @property
    def oauth_browser_cookie_path(self) -> str:
        return (
            "/" if self.oauth_browser_cookie_name.startswith("__Host-") else "/api/v1/auth/google"
        )


settings = Settings()
