import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, BigInteger, JSON, ForeignKey, Boolean, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
import enum


class DataSourceType(str, enum.Enum):
    questrade = "questrade"
    polygon = "polygon"
    alpha_vantage = "alpha_vantage"
    yahoo_finance = "yahoo_finance"


class Candle(Base):
    """OHLCV candle data — TimescaleDB hypertable partitioned by time."""
    __tablename__ = "candles"

    # Composite primary key
    time: Mapped[datetime] = mapped_column(DateTime, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(10), primary_key=True)
    source: Mapped[str] = mapped_column(String(50), primary_key=True, default="questrade")

    open: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    vwap: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)


class DataSourceConfig(Base):
    __tablename__ = "data_source_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    credentials_encrypted: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
