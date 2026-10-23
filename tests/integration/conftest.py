import logging
import os

import pytest

import app.services.storage as storage_service

RUN_INTEGRATION_ENV_VAR = "RUN_INTEGRATION"

logger = logging.getLogger(__name__)


def pytest_collection_modifyitems(config, items):
    """Collect integration tests always, but skip them unless opted in.

    Collecting them keeps the tests visible to editors and `--collect-only`;
    the skip mark keeps a plain `pytest` run off the real dev bucket.
    Opt in with `--integration` or RUN_INTEGRATION=1.
    """
    if config.getoption("--integration") or os.environ.get(RUN_INTEGRATION_ENV_VAR):
        return

    skip_integration = pytest.mark.skip(
        reason=(
            f"pass --integration or set {RUN_INTEGRATION_ENV_VAR}=1 "
            "to run tests against real R2"
        )
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture(autouse=True)
def stub_photo_storage():
    """Integration tests use the real dev-bucket credentials."""
    storage_service._get_s3_client.cache_clear()
    yield
    storage_service._get_s3_client.cache_clear()


@pytest.fixture()
def key_list():
    """
    Integration tests create real R2 objects. Need to delete objects after tests succeed
    """
    keys = []
    yield keys
    for key in keys:
        try:
            storage_service.delete_photo(object_key=key)
        except Exception:
            logger.warning("integration_cleanup_failed", extra={"object_key": key})
