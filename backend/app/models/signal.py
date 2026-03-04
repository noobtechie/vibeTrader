"""Trading signal — a detected pattern that may trigger a trade."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Numeric, JSON, ForeignKey, Uuid, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.enums import AutomationMode


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        # Fast lookup of pending signals per user
        Index("ix_signals_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("strategies.id", ondelete="SET NULL"),
        nullable=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    pattern_name: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # "bullish" | "bearish"
    confidence_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0.0)
    # automation_mode at time of signal: "full_auto" | "semi_auto"
    automation_mode: Mapped[str] = mapped_column(String(20), nullable=False, default=AutomationMode.semi_auto.value)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    # Snapshot of the last N candles used for detection (for audit/display)
    candles_snapshot: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Optional metadata from the pattern result
    pattern_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # For full-auto: execution note
    execution_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
