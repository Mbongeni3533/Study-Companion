"""Application configuration.

Settings are read from environment variables, then from a ``.env`` file in the
repository root or in ``backend/``. Everything has a usable development default
so the app boots with zero configuration, except the AI provider key which is
optional by design (the coach degrades to a rule-based engine without it).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    app_name: str = "Study Companion API"
    environment: str = "development"
    debug: bool = True
    cors_origins: str = "*"

    # --- Auth ---
    jwt_secret: str = "dev-only-secret-change-me-in-production-32b"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 30

    # --- Beta access control ---
    # When true, new accounts require an allowlisted email or a valid invite code.
    beta_invite_only: bool = False
    # Comma-separated emails that may register during the beta.
    beta_allowed_emails: str = ""
    # Comma-separated reusable invite codes (master codes). Database-backed
    # single-use codes are managed through the admin endpoints.
    beta_invite_codes: str = ""
    # Shared secret for the beta admin endpoints (X-Admin-Key header).
    beta_admin_key: str = ""
    # Optional public Google Doc with beta registration and feedback instructions.
    registration_doc_url: str = "https://docs.google.com/document/d/1PWpMViVx-JaVEbgsMR84oROHmxXr9YPHoqL3qpT5qnM/edit"

    # --- Email delivery for beta invites (Resend) ---
    resend_api_key: str | None = None
    resend_from_email: str = "Study Companion <onboarding@resend.dev>"
    # Whether guest/anonymous sessions are allowed. Disabled by default for beta.
    allow_anonymous_sessions: bool = False

    # --- Storage ---
    database_url: str = ""
    data_dir: Path = BACKEND_DIR / "data"
    max_file_size_mb: int = 50

    # --- OCR for scanned PDFs and images (optional deps, see requirements.txt) ---
    ocr_enabled: bool = True
    ocr_max_pages: int = 25
    ocr_dpi: int = 150

    # --- Study defaults ---
    default_daily_study_minutes: int = 60

    # --- AI provider (optional) ---
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    # Optional override for the endpoint the gateway forwards to (local fixture
    # or an already-authorized proxy). Empty means api.anthropic.com.
    anthropic_base_url: str | None = None
    ai_timeout_seconds: float = 45.0
    ai_max_tokens: int = 1200

    # --- Payments (phase 3, optional) ---
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'study_companion.db'}"

    @property
    def is_sqlite(self) -> bool:
        return self.sqlalchemy_url.startswith("sqlite")

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def allowed_origins(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
