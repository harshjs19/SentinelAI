from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "SentinelAI"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "sentinelai"
    postgres_user: str = "sentinelai"
    postgres_password: str = "sentinelai"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
