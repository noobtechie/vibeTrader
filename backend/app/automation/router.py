"""Automation & Scanning API."""
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import CurrentUser
from app.enums import AutomationMode
from app.models.signal import Signal
from app.models.strategy import Strategy, Playbook
from app.automation.scanner import scan, VALID_PATTERNS

_SYMBOL_RE = re.compile(r'^[A-Z0-9.\-]+$')

# "confirmed" is intentionally absent — confirm_signal transitions directly to "executed"
SIGNAL_STATUSES = frozenset({"pending", "rejected", "executed", "expired"})
DEFAULT_SIGNAL_TTL_MINUTES = 60
MAX_SCAN_CANDLES = 500
SIGNAL_SNAPSHOT_CANDLES = 10

router = APIRouter(prefix="/automation", tags=["automation"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CandlePayload(BaseModel):
    open: float
    high: float
    low: float
    close: float
    volume: int = 0

    @model_validator(mode="after")
    def check_ohlc(self) -> "CandlePayload":
        errors = []
        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            errors.append("OHLC prices must be positive")
        if self.high < self.low:
            errors.append("high must be >= low")
        if self.high < max(self.open, self.close):
            errors.append("high must be >= max(open, close)")
        if self.low > min(self.open, self.close):
            errors.append("low must be <= min(open, close)")
        if self.volume < 0:
            errors.append("volume must be >= 0")
        if errors:
            raise ValueError("; ".join(errors))
        return self


class ScanRequest(BaseModel):
    symbol: str
    candles: list[CandlePayload] = Field(..., min_length=1, max_length=MAX_SCAN_CANDLES)
    pattern_name: str
    pattern_params: Optional[dict] = None
    strategy_id: Optional[uuid.UUID] = None
    automation_mode: str = "semi_auto"
    ttl_minutes: int = DEFAULT_SIGNAL_TTL_MINUTES

    @field_validator("symbol", mode="after")
    @classmethod
    def symbol_format(cls, v):
        v = v.upper().strip()
        if len(v) > 20:
            raise ValueError("Symbol must be 20 characters or fewer")
        if not _SYMBOL_RE.match(v):
            raise ValueError("Symbol must contain only letters, digits, hyphens, and dots")
        return v

    @field_validator("automation_mode", mode="after")
    @classmethod
    def valid_mode(cls, v):
        valid = {AutomationMode.full_auto.value, AutomationMode.semi_auto.value}
        if v not in valid:
            raise ValueError(f"automation_mode must be one of {sorted(valid)}")
        return v

    @field_validator("pattern_params", mode="after")
    @classmethod
    def params_must_be_numeric(cls, v):
        if v is None:
            return v
        for key, val in v.items():
            if not isinstance(val, (int, float)):
                raise ValueError(
                    f"pattern_params values must be numeric; '{key}' got {type(val).__name__!r}"
                )
        return v

    @field_validator("ttl_minutes", mode="after")
    @classmethod
    def ttl_positive(cls, v):
        if not (1 <= v <= 1440):
            raise ValueError("ttl_minutes must be between 1 and 1440")
        return v


def _signal_dict(s: Signal) -> dict:
    return {
        "id": str(s.id),
        "user_id": str(s.user_id),
        "strategy_id": str(s.strategy_id) if s.strategy_id else None,
        "symbol": s.symbol,
        "pattern_name": s.pattern_name,
        "direction": s.direction,
        "confidence_score": float(s.confidence_score),
        "automation_mode": s.automation_mode,
        "status": s.status,
        "pattern_meta": s.pattern_meta,
        "execution_note": s.execution_note,
        "created_at": s.created_at.isoformat(),
        "expires_at": s.expires_at.isoformat() if s.expires_at else None,
        "resolved_at": s.resolved_at.isoformat() if s.resolved_at else None,
    }


async def _get_signal_or_404(db: AsyncSession, signal_id: uuid.UUID, user_id: uuid.UUID) -> Signal:
    result = await db.execute(
        select(Signal).where(Signal.id == signal_id, Signal.user_id == user_id)
    )
    sig = result.scalar_one_or_none()
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    return sig


# ─── Scan endpoint ────────────────────────────────────────────────────────────

@router.post("/scan", status_code=status.HTTP_201_CREATED)
async def run_scan(
    body: ScanRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Run a pattern scan on provided candles.

    If a pattern is detected, a Signal record is created:
    - semi_auto → status='pending' (awaiting user confirmation)
    - full_auto → status='executed' (automatically executed)

    Returns {"signal": <signal_dict>} if detected, {"signal": null} if not.
    """
    if body.pattern_name not in VALID_PATTERNS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown pattern '{body.pattern_name}'. Valid: {sorted(VALID_PATTERNS)}",
        )

    # Verify strategy ownership via Playbook join
    if body.strategy_id:
        strat_result = await db.execute(
            select(Strategy).join(
                Playbook, Strategy.playbook_id == Playbook.id
            ).where(
                Strategy.id == body.strategy_id,
                Playbook.user_id == current_user.id,
            )
        )
        if not strat_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Strategy not found")

    candles_raw = [c.model_dump() for c in body.candles]

    try:
        result = scan(body.pattern_name, candles_raw, body.pattern_params)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not result.detected:
        return {"signal": None, "detected": False}

    if body.automation_mode == "full_auto":
        sig_status = "executed"
        execution_note = "Auto-executed by full_auto scanner."
    else:
        sig_status = "pending"
        execution_note = None

    expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=body.ttl_minutes)

    signal = Signal(
        user_id=current_user.id,
        strategy_id=body.strategy_id,
        symbol=body.symbol,
        pattern_name=body.pattern_name,
        direction=result.direction,
        confidence_score=result.confidence,
        automation_mode=body.automation_mode,
        status=sig_status,
        candles_snapshot=candles_raw[-SIGNAL_SNAPSHOT_CANDLES:],
        pattern_meta=result.meta,
        execution_note=execution_note,
        expires_at=expires_at,
        resolved_at=datetime.now(tz=timezone.utc) if sig_status == "executed" else None,
    )
    db.add(signal)
    await db.flush()

    return {"signal": _signal_dict(signal), "detected": True}


# ─── Signal CRUD ──────────────────────────────────────────────────────────────

@router.get("/signals")
async def list_signals(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Optional[str] = Query(None, alias="status"),
    symbol: Optional[str] = Query(None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List signals for the current user, optionally filtered by status and/or symbol."""
    if status_filter and status_filter not in SIGNAL_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{status_filter}'. Valid: {sorted(SIGNAL_STATUSES)}",
        )

    base_where = [Signal.user_id == current_user.id]
    if status_filter:
        base_where.append(Signal.status == status_filter)
    if symbol:
        base_where.append(Signal.symbol == symbol.upper().strip())

    total_result = await db.execute(
        select(func.count()).select_from(Signal).where(*base_where)
    )
    total = total_result.scalar_one()

    query = (
        select(Signal).where(*base_where)
        .order_by(Signal.created_at.desc()).limit(limit).offset(offset)
    )
    result = await db.execute(query)
    signals = result.scalars().all()
    return {"signals": [_signal_dict(s) for s in signals], "count": len(signals), "total": total}


@router.get("/signals/{signal_id}")
async def get_signal(
    signal_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    sig = await _get_signal_or_404(db, signal_id, current_user.id)
    return {"signal": _signal_dict(sig)}


@router.post("/signals/{signal_id}/confirm", status_code=status.HTTP_200_OK)
async def confirm_signal(
    signal_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Confirm a pending semi-auto signal, triggering simulated execution.
    Only pending signals can be confirmed; transitions directly to 'executed'.
    """
    sig = await _get_signal_or_404(db, signal_id, current_user.id)
    if sig.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Signal is '{sig.status}', only 'pending' signals can be confirmed",
        )

    now = datetime.now(tz=timezone.utc)
    expires = sig.expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires < now:
        sig.status = "expired"
        sig.resolved_at = now
        await db.flush()
        raise HTTPException(status_code=409, detail="Signal has expired")

    sig.status = "executed"
    sig.resolved_at = now
    sig.execution_note = "Confirmed and executed by user."
    await db.flush()
    return {"signal": _signal_dict(sig)}


@router.post("/signals/{signal_id}/reject", status_code=status.HTTP_200_OK)
async def reject_signal(
    signal_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Reject/dismiss a pending signal."""
    sig = await _get_signal_or_404(db, signal_id, current_user.id)
    if sig.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Signal is '{sig.status}', only 'pending' signals can be rejected",
        )
    sig.status = "rejected"
    sig.resolved_at = datetime.now(tz=timezone.utc)
    await db.flush()
    return {"signal": _signal_dict(sig)}


@router.delete("/signals/{signal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_signal(
    signal_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Hard-delete a signal (any status)."""
    sig = await _get_signal_or_404(db, signal_id, current_user.id)
    await db.delete(sig)


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Automation dashboard summary:
    - active_strategies: strategies with automation_mode != 'disabled' and is_active=True
    - signal_counts_24h: per-status counts for signals created in the last 24 hours
    - recent_signals: last 5 signals (any status)
    """
    active_strats_result = await db.execute(
        select(func.count()).select_from(Strategy).join(
            Playbook, Strategy.playbook_id == Playbook.id
        ).where(
            Playbook.user_id == current_user.id,
            Strategy.automation_mode != "disabled",
            Strategy.is_active.is_(True),
        )
    )
    active_strategies = active_strats_result.scalar_one()

    since = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    counts_result = await db.execute(
        select(Signal.status, func.count().label("n"))
        .where(Signal.user_id == current_user.id, Signal.created_at >= since)
        .group_by(Signal.status)
    )
    signal_counts = {row.status: row.n for row in counts_result}

    recent_result = await db.execute(
        select(Signal)
        .where(Signal.user_id == current_user.id)
        .order_by(Signal.created_at.desc())
        .limit(5)
    )
    recent_signals = [_signal_dict(s) for s in recent_result.scalars().all()]

    return {
        "active_strategies": active_strategies,
        "signal_counts_24h": {
            "pending": signal_counts.get("pending", 0),
            "executed": signal_counts.get("executed", 0),
            "rejected": signal_counts.get("rejected", 0),
            "expired": signal_counts.get("expired", 0),
        },
        "recent_signals": recent_signals,
    }
