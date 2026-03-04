"""Backtesting API — submit runs, retrieve results."""
import re
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import CurrentUser
from app.models.backtest import BacktestResult
from app.backtesting.engine import CandleData, run_backtest, VALID_PATTERNS, PATTERN_PARAM_KEYS, MAX_CANDLES

_SYMBOL_RE = re.compile(r'^[A-Z0-9.\-]+$')

router = APIRouter(prefix="/backtest", tags=["backtesting"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class CandleInput(BaseModel):
    open: float
    high: float
    low: float
    close: float
    volume: int = 0

    @model_validator(mode="after")
    def check_ohlc_integrity(self) -> "CandleInput":
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


class RunBacktestRequest(BaseModel):
    candles: list[CandleInput]
    pattern_name: str
    pattern_params: Optional[dict] = None
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0
    initial_capital: float = 10_000.0
    symbol: Optional[str] = None
    strategy_id: Optional[uuid.UUID] = None

    @field_validator("stop_loss_pct", "take_profit_pct", mode="after")
    @classmethod
    def pct_positive(cls, v):
        if v <= 0:
            raise ValueError("Percentage must be > 0")
        return v

    @field_validator("initial_capital", mode="after")
    @classmethod
    def capital_positive(cls, v):
        if v <= 0:
            raise ValueError("initial_capital must be > 0")
        return v

    @field_validator("symbol", mode="after")
    @classmethod
    def symbol_format(cls, v):
        if v is not None:
            v = v.upper().strip()
            if len(v) > 20:
                raise ValueError("Symbol must be 20 characters or fewer")
            if not _SYMBOL_RE.match(v):
                raise ValueError("Symbol must contain only letters, digits, hyphens, and dots")
        return v


def _result_dict(r: BacktestResult) -> dict:
    return {
        "id": str(r.id),
        "user_id": str(r.user_id),
        "strategy_id": str(r.strategy_id) if r.strategy_id else None,
        "symbol": r.symbol,
        "status": r.status,
        "config": r.config,
        "results": r.results,
        "error_message": r.error_message,
        "created_at": r.created_at.isoformat(),
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/run", status_code=status.HTTP_201_CREATED)
async def run_backtest_endpoint(
    body: RunBacktestRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Run a synchronous backtest on the provided candle series."""
    if body.pattern_name not in VALID_PATTERNS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown pattern '{body.pattern_name}'. Valid: {sorted(VALID_PATTERNS)}",
        )
    if len(body.candles) > MAX_CANDLES:
        raise HTTPException(
            status_code=422,
            detail=f"Too many candles (max {MAX_CANDLES})",
        )

    # Validate pattern_params keys — reject unknown params with 422
    if body.pattern_params:
        allowed = PATTERN_PARAM_KEYS.get(body.pattern_name, set())
        unknown = set(body.pattern_params) - allowed
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown params for '{body.pattern_name}': {sorted(unknown)}. "
                       f"Allowed: {sorted(allowed)}",
            )

    candles = [CandleData(**c.model_dump()) for c in body.candles]
    config_dict = {
        "pattern_name": body.pattern_name,
        "pattern_params": body.pattern_params or {},
        "stop_loss_pct": body.stop_loss_pct,
        "take_profit_pct": body.take_profit_pct,
        "initial_capital": body.initial_capital,
    }

    # Run the engine — raise immediately on failure (not stored as error record)
    try:
        output = run_backtest(
            candles=candles,
            pattern_name=body.pattern_name,
            pattern_params=body.pattern_params,
            stop_loss_pct=body.stop_loss_pct,
            take_profit_pct=body.take_profit_pct,
            initial_capital=body.initial_capital,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}")

    bt_result = BacktestResult(
        user_id=current_user.id,
        strategy_id=body.strategy_id,
        symbol=body.symbol,
        status="complete",
        config=config_dict,
        results=output,
        completed_at=datetime.now(tz=timezone.utc),
    )
    db.add(bt_result)
    await db.flush()

    return {"result": _result_dict(bt_result)}


@router.get("/results")
async def list_results(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    symbol: Optional[str] = Query(None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List all backtest results for the current user."""
    query = select(BacktestResult).where(BacktestResult.user_id == current_user.id)
    if symbol:
        query = query.where(BacktestResult.symbol == symbol.upper().strip())
    query = query.order_by(BacktestResult.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    rows = result.scalars().all()
    return {"results": [_result_dict(r) for r in rows], "count": len(rows)}


@router.get("/results/{result_id}")
async def get_result(
    result_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Fetch a single backtest result by ID."""
    result = await db.execute(
        select(BacktestResult).where(
            BacktestResult.id == result_id,
            BacktestResult.user_id == current_user.id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return {"result": _result_dict(row)}


@router.delete("/results/{result_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_result(
    result_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a backtest result."""
    result = await db.execute(
        select(BacktestResult).where(
            BacktestResult.id == result_id,
            BacktestResult.user_id == current_user.id,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    await db.delete(row)
    await db.flush()
