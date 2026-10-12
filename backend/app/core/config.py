import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DATABASE_URL: str = "sqlite:///./paytrace.db"

    PAYPAL_CLIENT_ID: Optional[str] = ""
    PAYPAL_CLIENT_SECRET: Optional[str] = ""
    PAYPAL_ENVIRONMENT: str = "sandbox"
    PAYPAL_WEBHOOK_ID: Optional[str] = ""

    AI_PROVIDER: str = "openai"
    AI_API_KEY: Optional[str] = ""
    AI_MODEL: str = "gpt-4o-mini"

    DEMO_OPERATOR_TOKEN: str = "demo-operator-secret-token"
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    PUBLIC_API_BASE_URL: str = "http://localhost:8000"

    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    APIMATIC_API_KEY: Optional[str] = None

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
