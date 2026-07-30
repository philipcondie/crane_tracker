import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import get_session
from app.core.limiter import limiter
from app.main import app
from app.models.base import Crane
from app.services.geocode import GeocodeData

settings = get_settings()
engine = create_engine(settings.test_database_url)

TestingSessionLocal = sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    yield
    limiter.reset()


@pytest.fixture(autouse=True)
def stub_reverse_geocode(monkeypatch):
    monkeypatch.setattr(
        settings,
        "r2_public_base_url",
        "https://photos.example",
    )
    monkeypatch.setattr(
        "app.services.crane.reverse_geocode",
        lambda lat, lng: GeocodeData(
            city="San Francisco",
            neighborhood="Mission Bay",
        ),
    )


@pytest.fixture
def session():
    with TestingSessionLocal() as session:
        yield session
        session.execute(delete(Crane))
        session.commit()


@pytest.fixture
def client(session):
    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
