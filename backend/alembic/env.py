import asyncio
from logging.config import fileConfig
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base
from app.config import settings

# Import all models to register them with Base.metadata
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = settings.sync_database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = settings.database_url  # asyncpg driver required here
    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # TimescaleDB's CREATE EXTENSION must run outside a transaction (requires AUTOCOMMIT).
    async with connectable.execution_options(isolation_level="AUTOCOMMIT").connect() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))

    # Run the transactional migrations (creates all tables)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    # create_hypertable also requires AUTOCOMMIT and must run after the tables exist
    async with connectable.execution_options(isolation_level="AUTOCOMMIT").connect() as conn:
        await conn.execute(text(
            "SELECT create_hypertable('candles', 'time', if_not_exists => TRUE);"
        ))
        await conn.execute(text(
            "SELECT create_hypertable('risk_events', 'triggered_at', if_not_exists => TRUE);"
        ))

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
