"""Risk management service — validation, circuit breaker, event logging."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.risk import RiskSettings, RiskEvent
from app.models.trade import Trade
from app.enums import RiskEventType, LimitType, TradeStatus


class RiskViolation(Exception):
    """Raised when a trade would violate a risk limit."""

    def __init__(self, message: str, limit_type: str):
        super().__init__(message)
        self.limit_type = limit_type


async def get_or_create_settings(db: AsyncSession, user_id) -> RiskSettings:
    """Return user's risk settings, creating defaults if none exist.

    Uses a savepoint to handle the rare case of concurrent first-access
    without rolling back the parent transaction.
    """
    result = await db.execute(
        select(RiskSettings).where(RiskSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    if settings is None:
        try:
            async with db.begin_nested():
                settings = RiskSettings(user_id=user_id)
                db.add(settings)
                await db.flush()
        except IntegrityError:
            # Concurrent insert won; re-fetch
            result = await db.execute(
                select(RiskSettings).where(RiskSettings.user_id == user_id)
            )
            settings = result.scalar_one()
    return settings


async def _get_period_realized_loss(
    db: AsyncSession, user_id, since: datetime
) -> Decimal:
    """Sum absolute value of negative PnL for closed trades since a given datetime.

    Design decision: Only closed (realized) losses are counted, not open-position
    unrealized risk. This means the daily/weekly/monthly counters reflect actual
    P&L impact rather than potential exposure. Open-trade risk is captured
    separately via the per-trade check at order entry.
    """
    result = await db.execute(
        select(func.sum(Trade.pnl)).where(
            Trade.user_id == user_id,
            Trade.status == TradeStatus.closed.value,
            Trade.exit_time >= since,
            Trade.pnl < 0,
        )
    )
    total = result.scalar_one_or_none()
    return abs(total) if total else Decimal("0")


async def _record_event(
    db: AsyncSession,
    user_id,
    event_type: RiskEventType,
    limit_type: LimitType,
    current_value: Decimal,
    limit_value: Decimal,
    message: str,
) -> RiskEvent:
    event = RiskEvent(
        user_id=user_id,
        event_type=event_type.value,
        limit_type=limit_type.value,
        current_value=current_value,
        limit_value=limit_value,
        message=message,
    )
    db.add(event)
    await db.flush()
    return event


async def validate_pre_trade(
    db: AsyncSession,
    user_id,
    trade_risk: Decimal,
    account_equity: Optional[Decimal] = None,
) -> None:
    """
    Check that placing this trade won't violate any risk limits.

    trade_risk: dollar amount at risk (quantity * |entry_price - stop_loss|).
                Zero if no stop loss was provided — the per-trade check is skipped
                in that case, but a warning event is recorded and period checks
                still run against existing realized losses.

    account_equity: total equity used for percentage-mode limits. If the user has
                    configured use_percentage=True and this is None (equity could
                    not be fetched), a RiskViolation is raised to fail-safe.

    Raises RiskViolation if a limit would be exceeded.
    """
    settings = await get_or_create_settings(db, user_id)

    if settings.circuit_breaker_active:
        raise RiskViolation(
            "Circuit breaker is active. All new trades are blocked.",
            LimitType.circuit_breaker.value,
        )

    # Fail-safe: if the user relies on percentage limits but we cannot compute them,
    # block the trade rather than silently fall back to possibly-stale absolute limits.
    if settings.use_percentage and account_equity is None:
        raise RiskViolation(
            "Cannot validate risk: account equity is unavailable and risk settings "
            "use percentage mode. Try again or switch to absolute mode.",
            LimitType.per_trade.value,
        )

    def _limit(abs_limit: Decimal, pct_limit: Decimal) -> Decimal:
        if settings.use_percentage and account_equity:
            return account_equity * pct_limit
        return abs_limit

    # Warn (but don't block) when no stop loss was provided — audit trail only.
    if trade_risk == Decimal("0"):
        await _record_event(
            db, user_id,
            RiskEventType.warning, LimitType.per_trade,
            Decimal("0"), Decimal("0"),
            "Order placed without a stop loss price; per-trade risk check skipped.",
        )
    else:
        # Per-trade check
        per_trade_limit = _limit(settings.max_risk_per_trade, settings.max_risk_per_trade_pct)
        if trade_risk > per_trade_limit:
            await _record_event(
                db, user_id,
                RiskEventType.limit_hit, LimitType.per_trade,
                trade_risk, per_trade_limit,
                f"Trade risk ${trade_risk:.2f} exceeds per-trade limit ${per_trade_limit:.2f}",
            )
            raise RiskViolation(
                f"Trade risk ${trade_risk:.2f} exceeds per-trade limit ${per_trade_limit:.2f}",
                LimitType.per_trade.value,
            )

    now = datetime.now(tz=timezone.utc)

    # Daily check
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_loss = await _get_period_realized_loss(db, user_id, day_start)
    daily_limit = _limit(settings.max_risk_daily, settings.max_risk_daily_pct)
    if daily_loss + trade_risk > daily_limit:
        await _record_event(
            db, user_id,
            RiskEventType.limit_hit, LimitType.daily,
            daily_loss + trade_risk, daily_limit,
            f"Daily risk ${daily_loss + trade_risk:.2f} would exceed daily limit ${daily_limit:.2f}",
        )
        raise RiskViolation(
            f"Daily risk ${daily_loss + trade_risk:.2f} would exceed daily limit ${daily_limit:.2f}",
            LimitType.daily.value,
        )

    # Weekly check (Monday = start of week)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    weekly_loss = await _get_period_realized_loss(db, user_id, week_start)
    weekly_limit = _limit(settings.max_risk_weekly, settings.max_risk_weekly_pct)
    if weekly_loss + trade_risk > weekly_limit:
        await _record_event(
            db, user_id,
            RiskEventType.limit_hit, LimitType.weekly,
            weekly_loss + trade_risk, weekly_limit,
            f"Weekly risk ${weekly_loss + trade_risk:.2f} would exceed weekly limit ${weekly_limit:.2f}",
        )
        raise RiskViolation(
            f"Weekly risk ${weekly_loss + trade_risk:.2f} would exceed weekly limit ${weekly_limit:.2f}",
            LimitType.weekly.value,
        )

    # Monthly check
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_loss = await _get_period_realized_loss(db, user_id, month_start)
    monthly_limit = _limit(settings.max_risk_monthly, settings.max_risk_monthly_pct)
    if monthly_loss + trade_risk > monthly_limit:
        await _record_event(
            db, user_id,
            RiskEventType.limit_hit, LimitType.monthly,
            monthly_loss + trade_risk, monthly_limit,
            f"Monthly risk ${monthly_loss + trade_risk:.2f} would exceed monthly limit ${monthly_limit:.2f}",
        )
        raise RiskViolation(
            f"Monthly risk ${monthly_loss + trade_risk:.2f} would exceed monthly limit ${monthly_limit:.2f}",
            LimitType.monthly.value,
        )


async def activate_circuit_breaker(db: AsyncSession, user_id) -> RiskSettings:
    """Activate the circuit breaker. Idempotent — records one event per activation."""
    settings = await get_or_create_settings(db, user_id)
    if not settings.circuit_breaker_active:
        settings.circuit_breaker_active = True
        await _record_event(
            db, user_id,
            RiskEventType.circuit_break, LimitType.circuit_breaker,
            Decimal("0"), Decimal("0"),
            "Circuit breaker manually activated",
        )
        await db.flush()
    return settings


async def deactivate_circuit_breaker(db: AsyncSession, user_id) -> RiskSettings:
    """Deactivate the circuit breaker. Idempotent — records one event per deactivation."""
    settings = await get_or_create_settings(db, user_id)
    if settings.circuit_breaker_active:
        settings.circuit_breaker_active = False
        await _record_event(
            db, user_id,
            RiskEventType.circuit_break, LimitType.circuit_breaker,
            Decimal("0"), Decimal("0"),
            "Circuit breaker manually deactivated",
        )
        await db.flush()
    return settings
