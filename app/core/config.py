from functools import lru_cache

from pydantic import model_validator
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

    @model_validator(mode="after")
    def validate_r2_configuration(self) -> "Settings":
        values = {
            "R2_ENDPOINT_URL": self.r2_endpoint_url,
            "R2_ACCESS_KEY_ID": self.r2_access_key_id,
            "R2_SECRET_ACCESS_KEY": self.r2_secret_access_key,
            "R2_BUCKET_NAME": self.r2_bucket_name,
            "R2_PUBLIC_BASE_URL": self.r2_public_base_url,
        }
        missing = [name for name, value in values.items() if not value]
        deployed = self.environment.lower() in ("staging", "production")
        partially_configured = bool(any(values.values()) and missing)
        if (deployed and missing) or partially_configured:
            raise ValueError(
                f"{self.environment} requires complete R2 configuration when "
                f"photo storage is enabled; "
                f"missing: {', '.join(missing)}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
