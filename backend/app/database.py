from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_timescaledb_hypertables(session: AsyncSession) -> None:
    """Convert time-series tables to TimescaleDB hypertables."""
    hypertable_sql = [
        "SELECT create_hypertable('candles', 'time', if_not_exists => TRUE);",
        "SELECT create_hypertable('risk_events', 'triggered_at', if_not_exists => TRUE);",
    ]
    for sql in hypertable_sql:
        try:
            await session.execute(text(sql))
        except Exception:
            pass  # TimescaleDB extension may not be available in dev
    await session.commit()
