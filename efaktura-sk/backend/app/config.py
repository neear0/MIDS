"""Runtime settings, read from environment variables (prefix ``EFAKTURA_``)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EFAKTURA_", env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./efaktura.db"
    redis_url: str | None = None
    jwt_secret: str = "dev-only-secret-change-me-in-production-0000"
    jwt_ttl_minutes: int = 60 * 12
    cors_origins: list[str] = ["http://localhost:3000"]

    # Official EN 16931 + Peppol Schematron compiled to XSLT (optional).
    schematron_dir: Path = Path("./validation-artifacts")

    # AI: "heuristic" works offline; "anthropic" sends documents to the Claude API.
    extraction_provider: str = "heuristic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"

    # Peppol Access Point partner: "mock" for development, "http" for a partner REST API.
    peppol_provider: str = "mock"
    peppol_api_url: str | None = None
    peppol_api_key: str | None = None

    superfaktura_base_url: str = "https://moja.superfaktura.sk"
    superfaktura_sandbox_url: str = "https://sandbox.superfaktura.sk"

    # Fernet key used to encrypt third-party credentials at rest.
    secrets_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
