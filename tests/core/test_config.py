import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE_SETTINGS = {
    "database_url": "postgresql+psycopg://localhost/crane_spotter",
    "cors_origins": [],
    "ip_hash_salt": "test-salt",
}
R2_SETTINGS = {
    "r2_endpoint_url": "https://account.r2.cloudflarestorage.com",
    "r2_access_key_id": "access-key",
    "r2_secret_access_key": "secret-key",
    "r2_bucket_name": "crane-photos",
    "r2_public_base_url": "https://photos.example.com",
}


def test_development_allows_unconfigured_r2():
    settings = Settings(
        **BASE_SETTINGS,
        environment="development",
        _env_file=None,
    )

    assert settings.r2_bucket_name is None


def test_development_rejects_partial_r2_configuration():
    with pytest.raises(ValidationError, match="complete R2 configuration"):
        Settings(
            **BASE_SETTINGS,
            environment="development",
            r2_bucket_name="crane-photos",
            _env_file=None,
        )


def test_development_accepts_complete_r2_configuration():
    settings = Settings(
        **BASE_SETTINGS,
        **R2_SETTINGS,
        environment="development",
        _env_file=None,
    )

    assert settings.r2_bucket_name == "crane-photos"


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environments_require_complete_r2_configuration(environment):
    with pytest.raises(ValidationError, match="complete R2 configuration"):
        Settings(
            **BASE_SETTINGS,
            environment=environment,
            _env_file=None,
        )


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environments_accept_complete_r2_configuration(environment):
    settings = Settings(
        **BASE_SETTINGS,
        **R2_SETTINGS,
        environment=environment,
        _env_file=None,
    )

    assert settings.r2_bucket_name == "crane-photos"
