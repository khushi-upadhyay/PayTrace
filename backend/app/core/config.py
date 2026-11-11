from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional
import os
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = (BASE_DIR / "paytrace.db").as_posix()

class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DATABASE_URL: str = f"sqlite:///{DEFAULT_DB_PATH}"
    # Optional unpooled URL reserved for schema migrations and administrative
    # database operations (for example, Neon direct connections).
    DATABASE_URL_UNPOOLED: Optional[str] = None

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
            if not configured_model or configured_model.startswith("gpt-") or configured_model.startswith("grok") or "llama" in configured_model:
                return "openai/gpt-oss-120b"
            return configured_model
        return configured_model or "gpt-4o-mini"

    AUTH_SECRET_KEY: str = "dev-only-change-me-paytrace-auth-secret"
    RATE_LIMIT_ENABLED: bool = True
    MAX_ORDER_AMOUNT: float = 10000.00
    # Session cookie: "lax" works when the web app and API share a registrable domain (localhost, app.x.com + api.x.com).
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    AUTH_TOKEN_TTL_MINUTES: int = 720
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    APIMATIC_API_KEY: Optional[str] = None
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGSMITH_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: Optional[str] = "paytrace"
    LANGCHAIN_TRACING_V2: Optional[bool] = None
    LANGSMITH_TRACING: Optional[bool] = None
    SESSION_IDLE_TIMEOUT_SECONDS: int = 1800

    model_config = SettingsConfigDict(
        # Resolve project env files independently of the shell's current
        # directory so `uvicorn` works from either the repo root or backend/.
        env_file=(BASE_DIR / ".env", BASE_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def session_cookie_samesite(self) -> Literal["lax", "strict", "none"]:
        """Use cross-site cookies in deployed environments, while keeping localhost Lax by default."""
        local_frontend = urlsplit(self.FRONTEND_ORIGIN).hostname in {"localhost", "127.0.0.1", "::1"}
        if self.APP_ENV.strip().lower() in {"development", "test"} and local_frontend:
            return self.COOKIE_SAMESITE
        return "none"

    @property
    def cookie_secure(self) -> bool:
        return self.session_cookie_samesite == "none" or self.APP_ENV.strip().lower() not in {"development", "test"}

    @property
    def registration_open(self) -> bool:
        return self.APP_ENV.strip().lower() in {"development", "test"}

    @property
    def is_paypal_configured(self) -> bool:
        return bool(self.PAYPAL_CLIENT_ID and self.PAYPAL_CLIENT_SECRET)

    @property
    def is_ai_configured(self) -> bool:
        key = self.effective_ai_api_key
        return bool(key and len(key) > 5)

    @property
    def is_langsmith_tracing_enabled(self) -> bool:
        explicit = self.LANGSMITH_TRACING
        if explicit is None:
            explicit = self.LANGCHAIN_TRACING_V2
        return bool((self.LANGSMITH_API_KEY or self.LANGCHAIN_API_KEY) and explicit is not False)

settings = Settings()

# LangGraph emits LangSmith traces when a key is supplied. Respect an explicit
# tracing toggle; otherwise enable tracing automatically when the key exists.
_langsmith_key = (settings.LANGSMITH_API_KEY or settings.LANGCHAIN_API_KEY or "").strip()
if _langsmith_key:
    os.environ.setdefault("LANGSMITH_API_KEY", _langsmith_key)
    os.environ.setdefault("LANGCHAIN_API_KEY", _langsmith_key)
    tracing_enabled = settings.LANGSMITH_TRACING
    if tracing_enabled is None:
        tracing_enabled = settings.LANGCHAIN_TRACING_V2
    if tracing_enabled is None:
        tracing_enabled = True
    os.environ["LANGSMITH_TRACING"] = str(tracing_enabled).lower()
    os.environ["LANGCHAIN_TRACING_V2"] = str(tracing_enabled).lower()
    if settings.LANGCHAIN_PROJECT:
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.LANGCHAIN_PROJECT)
