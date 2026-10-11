"""Reference API settings using the touchpoint-taxonomy get_settings pattern."""

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Local API configuration; no database or cloud credentials are required yet."""

    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = Field(default="pg-task-engine API", min_length=1)
    DEBUG: bool = False
    APP_ROOT_PATH: str = Field(default="", pattern=r"^(/.*)?$")
    CORS_ORIGINS: list[str] = Field(default_factory=list)


def get_settings() -> Settings:
    """Read settings when constructing the API, not when importing the library."""
    return Settings(_env_file=os.environ.get("SETTINGS_ENV", ".env"))
