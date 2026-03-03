import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, Boolean, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class RiskEventType(str, enum.Enum):
    limit_hit = "limit_hit"
    circuit_break = "circuit_break"
    warning = "warning"


class LimitType(str, enum.Enum):
    per_trade = "per_trade"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class RiskSettings(Base):
    __tablename__ = "risk_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    max_risk_per_trade: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("500.00")
    )
    max_risk_per_trade_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.01")
    )
    max_risk_daily: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("1500.00")
    )
    max_risk_daily_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.03")
    )
    max_risk_weekly: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("3000.00")
    )
    max_risk_weekly_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.06")
    )
    max_risk_monthly: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("7500.00")
    )
    max_risk_monthly_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.15")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CAD")
    use_percentage: Mapped[bool] = mapped_column(Boolean, default=True)
    circuit_breaker_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="risk_settings")  # type: ignore[name-defined]


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    limit_type: Mapped[str] = mapped_column(String(50), nullable=False)
    current_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    limit_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
