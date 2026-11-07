"""Application settings, read from the environment.

Every value has a development default so the app boots with no configuration,
but the two that matter for security -- `SECRET_KEY` and `DATABASE_URL` -- are
checked at startup in production and the app refuses to run with the defaults.
That is deliberate: a JWT secret that ships as "change-me" is worse than no
secret at all, because it looks configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# The value that must never reach production.
INSECURE_DEFAULT_SECRET = "dev-insecure-secret-change-me"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Settings:
    """Runtime configuration."""

    app_name: str = "Iksir"
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: _env_bool("DEBUG", False))

    # Auth
    secret_key: str = field(
        default_factory=lambda: os.getenv("SECRET_KEY", INSECURE_DEFAULT_SECRET)
    )
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = field(
        default_factory=lambda: _env_int("ACCESS_TOKEN_MINUTES", 60 * 24)
    )
    bcrypt_rounds: int = field(default_factory=lambda: _env_int("BCRYPT_ROUNDS", 12))

    # Database. SQLite by default so a fresh clone runs with zero setup; point
    # DATABASE_URL at Postgres for anything real.
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./iksir.db")
    )

    # CORS: an explicit allow-list, never "*" in production.
    cors_origins: list[str] = field(
        default_factory=lambda: _env_list(
            "CORS_ORIGINS",
            ["http://localhost:8000", "http://127.0.0.1:8000"],
        )
    )

    # Rate limiting (requests per window, per client IP).
    rate_limit_requests: int = field(default_factory=lambda: _env_int("RATE_LIMIT_REQUESTS", 120))
    rate_limit_window_seconds: int = field(
        default_factory=lambda: _env_int("RATE_LIMIT_WINDOW_SECONDS", 60)
    )
    auth_rate_limit_requests: int = field(
        default_factory=lambda: _env_int("AUTH_RATE_LIMIT_REQUESTS", 10)
    )

    # Screening limits, so one request cannot pin the CPU.
    max_library_size: int = field(default_factory=lambda: _env_int("MAX_LIBRARY_SIZE", 200))
    max_smiles_length: int = field(default_factory=lambda: _env_int("MAX_SMILES_LENGTH", 2000))

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in ("production", "prod")

    def validate(self) -> list[str]:
        """Return a list of configuration problems that must block startup."""
        problems: list[str] = []
        if self.is_production:
            if self.secret_key == INSECURE_DEFAULT_SECRET:
                problems.append(
                    "SECRET_KEY is still the development default; set a real secret "
                    "before running in production"
                )
            if len(self.secret_key) < 32:
                problems.append("SECRET_KEY should be at least 32 characters")
            if "*" in self.cors_origins:
                problems.append("CORS_ORIGINS must not contain '*' in production")
            if self.database_url.startswith("sqlite"):
                problems.append("DATABASE_URL points at SQLite; use Postgres in production")
        return problems


settings = Settings()
