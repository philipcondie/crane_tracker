from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env"}
    database_url: str
    test_database_url: str
    environment: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
