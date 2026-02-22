"""
Application configuration loaded from environment variables.
"""
from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Kalpi Portfolio Execution Engine"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Security
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Database — defaults to SQLite for local dev, override with PostgreSQL for production
    DATABASE_URL: str = "sqlite+aiosqlite:///./kalpi.db"

    # Paper Trading (simulate orders without real execution)
    PAPER_TRADING: bool = True

    # Notification
    WEBHOOK_URL: str = "http://localhost:8000/api/v1/notifications/webhook-receiver"

    # CORS
    CORS_ORIGINS: str = '["http://localhost:3000","http://localhost:5173"]'

    # Rate limiting
    MAX_ORDERS_PER_SECOND: int = 5
    MAX_RETRY_ATTEMPTS: int = 3
    RETRY_DELAY_SECONDS: float = 2.0

    @property
    def cors_origins_list(self) -> List[str]:
        try:
            return json.loads(self.CORS_ORIGINS)
        except Exception:
            return ["http://localhost:3000", "http://localhost:5173"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()


