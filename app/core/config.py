from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env"}
    database_url: str
    test_database_url: str | None = None
    environment: str
    cors_origins: list[str]
    gone_report_threshold: int = 3
    ip_hash_salt: str
    create_rate_limit: str = "5/hr"
    r2_endpoint_url: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket_name: str | None = None
    r2_public_base_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
