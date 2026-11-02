from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = (BASE_DIR / "paytrace.db").as_posix()

class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DATABASE_URL: str = f"sqlite:///{DEFAULT_DB_PATH}"

    PAYPAL_CLIENT_ID: Optional[str] = ""
    PAYPAL_CLIENT_SECRET: Optional[str] = ""
    PAYPAL_MODE: Literal["sandbox", "live"] = "sandbox"
    PAYPAL_WEBHOOK_ID: Optional[str] = ""

    @property
    def paypal_mode(self) -> str:
        """Returns the explicitly configured PayPal environment."""
        return self.PAYPAL_MODE

    AI_PROVIDER: str = "openai"
    AI_API_KEY: Optional[str] = ""
    AI_MODEL: str = "gpt-4o-mini"
    AI_BASE_URL: Optional[str] = None
    GROK_API_KEY: Optional[str] = None
    XAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    @property
    def effective_ai_provider(self) -> str:
        """Normalized AI provider: 'openai', 'grok', 'xai', or 'groq'."""
        prov = (self.AI_PROVIDER or "").strip().lower()
        if prov in ("grok", "xai"):
            key = self.effective_ai_api_key
            if key and key.startswith("gsk_"):
                return "groq"
            return "grok"
        if prov == "groq":
            return "groq"
        return "openai"

    @property
    def effective_ai_api_key(self) -> str:
        """Resolves the active API key across provider-specific and general settings."""
        if self.AI_API_KEY and len(self.AI_API_KEY.strip()) > 0:
            return self.AI_API_KEY.strip()
        prov = (self.AI_PROVIDER or "").strip().lower()
        if prov in ("grok", "xai"):
            return (self.XAI_API_KEY or self.GROK_API_KEY or self.GROQ_API_KEY or "").strip()
        if prov == "groq":
            return (self.GROQ_API_KEY or "").strip()
        return (self.OPENAI_API_KEY or "").strip()

    @property
    def effective_ai_endpoint(self) -> str:
        """Resolves chat completions API endpoint for OpenAI, Grok (xAI), or Groq."""
        if self.AI_BASE_URL and self.AI_BASE_URL.strip():
            url = self.AI_BASE_URL.strip().rstrip("/")
            if not url.endswith("/chat/completions"):
                url = f"{url}/chat/completions"
            return url
        prov = self.effective_ai_provider
        if prov == "grok":
            return "https://api.x.ai/v1/chat/completions"
        elif prov == "groq":
            return "https://api.groq.com/openai/v1/chat/completions"
        return "https://api.openai.com/v1/chat/completions"

    @property
    def effective_ai_model(self) -> str:
        """Resolves the model name, providing suitable defaults if switching providers."""
        prov = self.effective_ai_provider
        configured_model = (self.AI_MODEL or "").strip()
        if prov == "grok":
            if not configured_model or configured_model.startswith("gpt-"):
                return "grok-2-latest"
            return configured_model
        elif prov == "groq":
            if not configured_model or configured_model.startswith("gpt-") or configured_model.startswith("grok"):
                return "llama-3.3-70b-versatile"
            return configured_model
        return configured_model or "gpt-4o-mini"

    DEMO_OPERATOR_TOKEN: str = "demo-operator-secret-token"
    AUTH_SECRET_KEY: str = "dev-only-change-me-paytrace-auth-secret"
    AUTH_TOKEN_TTL_MINUTES: int = 720
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    APIMATIC_API_KEY: Optional[str] = None
    SESSION_IDLE_TIMEOUT_SECONDS: int = 1800

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_paypal_configured(self) -> bool:
        return bool(self.PAYPAL_CLIENT_ID and self.PAYPAL_CLIENT_SECRET)

    @property
    def is_ai_configured(self) -> bool:
        key = self.effective_ai_api_key
        return bool(key and len(key) > 5)

settings = Settings()
