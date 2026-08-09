from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()

DATABASE_URL = settings.database_url

WEBSERVER_POOL_SIZE = 10
WEBSERVER_MAX_OVERFLOW = 20
WEBSERVER_POOL_PRE_PING = True

WORKER_POOL_SIZE = 2
WORKER_MAX_OVERFLOW = 4
WORKER_POOL_PRE_PING = True


@lru_cache
def get_engine(
    *, database_url: str, pool_size: int, max_overflow: int, pool_pre_ping: bool
) -> Engine:
    return create_engine(
        url=database_url,
        plugins=["geoalchemy2"],
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
    )


@lru_cache
def get_sessionmaker(engine: Engine) -> sessionmaker:
    return sessionmaker(engine, expire_on_commit=False)


def _sessionmaker_for(profile: str) -> sessionmaker:
    if profile == "webserver":
        engine = get_engine(
            database_url=DATABASE_URL,
            pool_size=WEBSERVER_POOL_SIZE,
            max_overflow=WEBSERVER_MAX_OVERFLOW,
            pool_pre_ping=WEBSERVER_POOL_PRE_PING,
        )
        return get_sessionmaker(engine)
    elif profile == "worker":
        engine = get_engine(
            database_url=DATABASE_URL,
            pool_size=WORKER_POOL_SIZE,
            max_overflow=WORKER_MAX_OVERFLOW,
            pool_pre_ping=WORKER_POOL_PRE_PING,
        )
        return get_sessionmaker(engine)

    raise ValueError("Invalid session profile")


def get_session():
    SessionLocal = _sessionmaker_for("webserver")
    with SessionLocal() as session:
        yield session


@contextmanager
def session_scope(profile: str):
    SessionLocal = _sessionmaker_for(profile)
    session = SessionLocal()
    try:
        yield session
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
