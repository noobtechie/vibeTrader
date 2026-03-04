"""Strategies API — Playbook CRUD, Strategy CRUD, pattern detection."""
import uuid
from datetime import datetime
from typing import Annotated, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.dependencies import CurrentUser
from app.enums import AutomationMode
from app.models.strategy import Playbook, Strategy

VALID_PATTERNS = frozenset({"pin_bar", "breakout", "vwap_bounce", "volume_spike", "flag"})
MAX_CANDLES = 1000

router = APIRouter(prefix="/strategies", tags=["strategies"])


# ─── Pydantic schemas ──────────────────────────────────────────────────────────

class PlaybookCreate(BaseModel):
    name: str
    description: Optional[str] = None
    goals: Optional[dict] = None
    theory: Optional[str] = None
    security_criteria: Optional[dict] = None
    context_rules: Optional[list] = None
    trigger_rules: Optional[list] = None
    management_rules: Optional[dict] = None
    sizing_tiers: Optional[list] = None
    tracking_abbreviations: Optional[dict] = None
    questions: Optional[list] = None
    ideas: Optional[list] = None


class PlaybookUpdate(PlaybookCreate):
    name: Optional[str] = None  # type: ignore[assignment]
    is_active: Optional[bool] = None


class StrategyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    automation_mode: str = AutomationMode.disabled.value
    config: Optional[dict] = None
    watchlist: Optional[list] = None


class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    automation_mode: Optional[str] = None
    is_active: Optional[bool] = None
    config: Optional[dict] = None
    watchlist: Optional[list] = None


def _playbook_dict(p: Playbook) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "goals": p.goals,
        "theory": p.theory,
        "security_criteria": p.security_criteria,
        "context_rules": p.context_rules,
        "trigger_rules": p.trigger_rules,
        "management_rules": p.management_rules,
        "sizing_tiers": p.sizing_tiers,
        "tracking_abbreviations": p.tracking_abbreviations,
        "questions": p.questions,
        "ideas": p.ideas,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def _strategy_dict(s: Strategy) -> dict:
    return {
        "id": str(s.id),
        "playbook_id": str(s.playbook_id),
        "name": s.name,
        "description": s.description,
        "automation_mode": s.automation_mode,
        "is_active": s.is_active,
        "config": s.config,
        "watchlist": s.watchlist,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
    }


async def _get_playbook_or_404(
    db: AsyncSession, playbook_id: uuid.UUID, user_id: uuid.UUID
) -> Playbook:
    result = await db.execute(
        select(Playbook).where(
            Playbook.id == playbook_id,
            Playbook.user_id == user_id,
        )
    )
    pb = result.scalar_one_or_none()
    if not pb:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return pb


async def _get_strategy_or_404(
    db: AsyncSession, strategy_id: uuid.UUID, user_id: uuid.UUID
) -> Strategy:
    result = await db.execute(
        select(Strategy)
        .join(Playbook, Strategy.playbook_id == Playbook.id)
        .where(
            Strategy.id == strategy_id,
            Playbook.user_id == user_id,
        )
    )
    strat = result.scalar_one_or_none()
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strat


# ─── Playbook endpoints ────────────────────────────────────────────────────────

@router.get("/playbooks")
async def list_playbooks(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Playbook).where(Playbook.user_id == current_user.id)
        .order_by(Playbook.created_at.desc())
    )
    playbooks = result.scalars().all()
    return {"playbooks": [_playbook_dict(p) for p in playbooks]}


@router.post("/playbooks", status_code=status.HTTP_201_CREATED)
async def create_playbook(
    body: PlaybookCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    pb = Playbook(user_id=current_user.id, **body.model_dump())
    db.add(pb)
    await db.flush()
    return {"playbook": _playbook_dict(pb)}


@router.get("/playbooks/{playbook_id}")
async def get_playbook(
    playbook_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    pb = await _get_playbook_or_404(db, playbook_id, current_user.id)
    return {"playbook": _playbook_dict(pb)}


@router.put("/playbooks/{playbook_id}")
async def update_playbook(
    playbook_id: uuid.UUID,
    body: PlaybookUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    pb = await _get_playbook_or_404(db, playbook_id, current_user.id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(pb, field, value)
    await db.flush()
    return {"playbook": _playbook_dict(pb)}


@router.delete("/playbooks/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playbook(
    playbook_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    pb = await _get_playbook_or_404(db, playbook_id, current_user.id)
    await db.delete(pb)
    await db.flush()


# ─── Strategy endpoints ────────────────────────────────────────────────────────

@router.get("/playbooks/{playbook_id}/strategies")
async def list_strategies(
    playbook_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_playbook_or_404(db, playbook_id, current_user.id)
    result = await db.execute(
        select(Strategy).where(Strategy.playbook_id == playbook_id)
        .order_by(Strategy.created_at.desc())
    )
    strategies = result.scalars().all()
    return {"strategies": [_strategy_dict(s) for s in strategies]}


@router.post("/playbooks/{playbook_id}/strategies", status_code=status.HTTP_201_CREATED)
async def create_strategy(
    playbook_id: uuid.UUID,
    body: StrategyCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_playbook_or_404(db, playbook_id, current_user.id)
    # Validate automation_mode
    try:
        AutomationMode(body.automation_mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid automation_mode. Valid values: {[e.value for e in AutomationMode]}",
        )
    strat = Strategy(playbook_id=playbook_id, **body.model_dump())
    db.add(strat)
    await db.flush()
    return {"strategy": _strategy_dict(strat)}


@router.get("/strategies/{strategy_id}")
async def get_strategy(
    strategy_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strat = await _get_strategy_or_404(db, strategy_id, current_user.id)
    return {"strategy": _strategy_dict(strat)}


@router.put("/strategies/{strategy_id}")
async def update_strategy(
    strategy_id: uuid.UUID,
    body: StrategyUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strat = await _get_strategy_or_404(db, strategy_id, current_user.id)
    update_data = body.model_dump(exclude_none=True)

    if "automation_mode" in update_data:
        try:
            AutomationMode(update_data["automation_mode"])
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid automation_mode. Valid values: {[e.value for e in AutomationMode]}",
            )

    for field, value in update_data.items():
        setattr(strat, field, value)
    await db.flush()
    return {"strategy": _strategy_dict(strat)}


@router.delete("/strategies/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    strat = await _get_strategy_or_404(db, strategy_id, current_user.id)
    await db.delete(strat)
    await db.flush()


# ─── Pattern detection endpoint ────────────────────────────────────────────────

class CandleInput(BaseModel):
    open: float
    high: float
    low: float
    close: float
    volume: int = 0

    @model_validator(mode="after")
    def check_ohlc_integrity(self) -> "CandleInput":
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.high < self.open or self.high < self.close:
            raise ValueError("high must be >= open and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be <= open and close")
        if self.volume < 0:
            raise ValueError("volume must be >= 0")
        return self


class PatternDetectRequest(BaseModel):
    candles: list[CandleInput]
    patterns: list[str]  # e.g. ["pin_bar", "breakout", "vwap_bounce", "volume_spike", "flag"]


@router.post("/patterns/detect")
async def detect_patterns(
    body: PatternDetectRequest,
    current_user: CurrentUser,
):
    """
    Run pattern detectors on the provided candle series.
    Returns detection results for each requested pattern.
    Requires authentication. Maximum 1000 candles per request.
    """
    from decimal import Decimal as D

    if not body.candles:
        raise HTTPException(status_code=422, detail="candles list must not be empty")
    if len(body.candles) > MAX_CANDLES:
        raise HTTPException(
            status_code=422,
            detail=f"candles must not exceed {MAX_CANDLES} entries",
        )
    unknown = set(body.patterns) - VALID_PATTERNS
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown patterns: {sorted(unknown)}. Valid: {sorted(VALID_PATTERNS)}",
        )

    opens = [D(str(c.open)) for c in body.candles]
    highs = [D(str(c.high)) for c in body.candles]
    lows = [D(str(c.low)) for c in body.candles]
    closes = [D(str(c.close)) for c in body.candles]
    volumes = [c.volume for c in body.candles]

    results: dict[str, Any] = {}

    if "pin_bar" in body.patterns:
        from app.strategies.patterns.pin_bar import detect_pin_bar
        r = detect_pin_bar(opens, highs, lows, closes)
        results["pin_bar"] = {
            "detected": r.detected,
            "direction": r.direction,
            "ratio": float(r.ratio),
        }

    if "breakout" in body.patterns:
        from app.strategies.patterns.breakout import detect_breakout
        r = detect_breakout(highs, lows, closes)
        results["breakout"] = {
            "detected": r.detected,
            "direction": r.direction,
            "breakout_price": float(r.breakout_price),
            "range_high": float(r.range_high),
            "range_low": float(r.range_low),
        }

    if "vwap_bounce" in body.patterns:
        from app.strategies.patterns.vwap_bounce import detect_vwap_bounce
        r = detect_vwap_bounce(highs, lows, closes, volumes)
        results["vwap_bounce"] = {
            "detected": r.detected,
            "direction": r.direction,
            "vwap": float(r.vwap),
            "touch_proximity_pct": float(r.touch_proximity_pct),
        }

    if "volume_spike" in body.patterns:
        from app.strategies.patterns.volume_spike import detect_volume_spike
        r = detect_volume_spike(volumes)
        results["volume_spike"] = {
            "detected": r.detected,
            "spike_ratio": float(r.spike_ratio),
            "average_volume": float(r.average_volume),
        }

    if "flag" in body.patterns:
        from app.strategies.patterns.flags import detect_flag
        r = detect_flag(highs, lows, closes)
        results["flag"] = {
            "detected": r.detected,
            "direction": r.direction,
            "pole_gain_pct": float(r.pole_gain_pct),
            "flag_depth_pct": float(r.flag_depth_pct),
        }

    return {"patterns": results, "candle_count": len(body.candles)}
