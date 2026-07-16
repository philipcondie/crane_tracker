import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.test_database_url)

TestingSessionLocal = sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def session():
    with TestingSessionLocal() as session:
        yield session
        session.rollback()
