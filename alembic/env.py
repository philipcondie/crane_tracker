from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.core.config import Settings, get_settings
from app.models.base import Base


def resolve_database_url(settings: Settings) -> str:
    """Pick the migration target database based on the environment.

    ``ENVIRONMENT=test`` migrates the test database; every other recognized
    environment migrates the primary one. Unknown values raise rather than
    silently defaulting, so a typo cannot point DDL at the wrong database.
    """
    if settings.environment == "test":
        if not settings.test_database_url:
            raise ValueError(
                "ENVIRONMENT=test requires TEST_DATABASE_URL to be set."
            )
        return settings.test_database_url

    if settings.environment not in ("dev", "development", "staging", "production"):
        raise ValueError(
            f"Unknown ENVIRONMENT {settings.environment!r}; expected one of "
            "'dev', 'development', 'staging', 'production', 'test'."
        )

    return settings.database_url


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
settings = get_settings()

config.set_main_option(
    "sqlalchemy.url",
    resolve_database_url(settings),
)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = resolve_database_url(get_settings())
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
