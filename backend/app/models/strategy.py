import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Text, JSON, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class AutomationMode(str, enum.Enum):
    disabled = "disabled"
    semi_auto = "semi_auto"
    full_auto = "full_auto"


class Playbook(Base):
    """10-category JumpStart Trading playbook."""
    __tablename__ = "playbooks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 10 JumpStart categories (stored as JSON)
    goals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    theory: Mapped[str | None] = mapped_column(Text, nullable=True)
    security_criteria: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context_rules: Mapped[list | None] = mapped_column(JSON, nullable=True)
    trigger_rules: Mapped[list | None] = mapped_column(JSON, nullable=True)
    management_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sizing_tiers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tracking_abbreviations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    questions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ideas: Mapped[list | None] = mapped_column(JSON, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="playbooks")  # type: ignore[name-defined]
    strategies: Mapped[list["Strategy"]] = relationship(
        back_populates="playbook", cascade="all, delete-orphan"
    )


class Strategy(Base):
    """A runnable strategy linked to a playbook."""
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    playbook_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    automation_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AutomationMode.disabled.value
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    watchlist: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    playbook: Mapped["Playbook"] = relationship(back_populates="strategies")
