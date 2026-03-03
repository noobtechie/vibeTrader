import uuid
from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, Text, JSON, ForeignKey, Integer, Boolean, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trade_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("trades.id", ondelete="SET NULL"), nullable=True
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    screenshots: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # JumpStart tracking abbreviations
    context_abbreviation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    trigger_abbreviation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    management_abbreviation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sizing_tier: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Process tracking
    confidence_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    followed_playbook: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    lessons_learned: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="journal_entries")  # type: ignore[name-defined]
    trade: Mapped["Trade"] = relationship(back_populates="journal_entries")  # type: ignore[name-defined]
