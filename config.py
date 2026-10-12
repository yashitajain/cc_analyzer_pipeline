"""
Environment configuration for the backend.
Loads from .env file or environment variables.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """App settings loaded from environment."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost/cc_pipeline"

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24

    # Claude API
    ANTHROPIC_API_KEY: str = ""
    # Redis configuration
    REDIS_URL: str = "redis://localhost:6379"
    # App
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()




