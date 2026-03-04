"""Risk management API endpoints."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.dependencies import CurrentUser
from app.models.risk import RiskEvent
from app.risk.service import (
    get_or_create_settings,
    activate_circuit_breaker,
    deactivate_circuit_breaker,
)

router = APIRouter(prefix="/risk", tags=["risk"])


class RiskSettingsUpdate(BaseModel):
    max_risk_per_trade: Optional[Decimal] = None
    max_risk_per_trade_pct: Optional[Decimal] = None
    max_risk_daily: Optional[Decimal] = None
    max_risk_daily_pct: Optional[Decimal] = None
    max_risk_weekly: Optional[Decimal] = None
    max_risk_weekly_pct: Optional[Decimal] = None
    max_risk_monthly: Optional[Decimal] = None
    max_risk_monthly_pct: Optional[Decimal] = None
    currency: Optional[str] = None
    use_percentage: Optional[bool] = None

    @field_validator(
        "max_risk_per_trade", "max_risk_daily", "max_risk_weekly", "max_risk_monthly",
        mode="before",
    )
    @classmethod
    def must_be_positive(cls, v):
        if v is not None and Decimal(str(v)) <= 0:
            raise ValueError("Risk limits must be greater than zero")
        return v

    @field_validator(
        "max_risk_per_trade_pct", "max_risk_daily_pct",
        "max_risk_weekly_pct", "max_risk_monthly_pct",
        mode="before",
    )
    @classmethod
    def must_be_valid_percentage(cls, v):
        if v is not None:
            d = Decimal(str(v))
            if not (Decimal("0") < d <= Decimal("1")):
                raise ValueError("Percentage limits must be between 0 (exclusive) and 1 (inclusive)")
        return v

    @field_validator("currency", mode="before")
    @classmethod
    def must_be_iso_currency(cls, v):
        if v is not None and (not isinstance(v, str) or len(v) != 3 or not v.isalpha()):
            raise ValueError("currency must be a 3-letter ISO currency code (e.g. CAD, USD)")
        return v.upper() if v else v


class RiskSettingsResponse(BaseModel):
    id: str
    max_risk_per_trade: Decimal
    max_risk_per_trade_pct: Decimal
    max_risk_daily: Decimal
    max_risk_daily_pct: Decimal
    max_risk_weekly: Decimal
    max_risk_weekly_pct: Decimal
    max_risk_monthly: Decimal
    max_risk_monthly_pct: Decimal
    currency: str
    use_percentage: bool
    circuit_breaker_active: bool
    updated_at: datetime


def _settings_response(s) -> RiskSettingsResponse:
    return RiskSettingsResponse(
        id=str(s.id),
        max_risk_per_trade=s.max_risk_per_trade,
        max_risk_per_trade_pct=s.max_risk_per_trade_pct,
        max_risk_daily=s.max_risk_daily,
        max_risk_daily_pct=s.max_risk_daily_pct,
        max_risk_weekly=s.max_risk_weekly,
        max_risk_weekly_pct=s.max_risk_weekly_pct,
        max_risk_monthly=s.max_risk_monthly,
        max_risk_monthly_pct=s.max_risk_monthly_pct,
        currency=s.currency,
        use_percentage=s.use_percentage,
        circuit_breaker_active=s.circuit_breaker_active,
        updated_at=s.updated_at,
    )


@router.get("/settings", response_model=RiskSettingsResponse)
async def get_risk_settings(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    settings = await get_or_create_settings(db, current_user.id)
    return _settings_response(settings)


@router.put("/settings", response_model=RiskSettingsResponse)
async def update_risk_settings(
    body: RiskSettingsUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    settings = await get_or_create_settings(db, current_user.id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(settings, field, value)
    await db.flush()
    return _settings_response(settings)


@router.get("/events")
async def get_risk_events(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
):
    result = await db.execute(
        select(RiskEvent)
        .where(RiskEvent.user_id == current_user.id)
        .order_by(RiskEvent.triggered_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    return {
        "events": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "limit_type": e.limit_type,
                "current_value": float(e.current_value),
                "limit_value": float(e.limit_value),
                "triggered_at": e.triggered_at.isoformat(),
                "message": e.message,
            }
            for e in events
        ]
    }


@router.post("/circuit-breaker/activate")
async def activate_cb(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    settings = await activate_circuit_breaker(db, current_user.id)
    return {"circuit_breaker_active": settings.circuit_breaker_active}


@router.post("/circuit-breaker/deactivate")
async def deactivate_cb(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    settings = await deactivate_circuit_breaker(db, current_user.id)
    return {"circuit_breaker_active": settings.circuit_breaker_active}
