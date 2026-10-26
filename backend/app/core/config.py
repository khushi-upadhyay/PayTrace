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
        return bool(self.AI_API_KEY and len(self.AI_API_KEY.strip()) > 5)

settings = Settings()
