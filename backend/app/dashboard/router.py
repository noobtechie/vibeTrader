"""Comprehensive dashboard API — aggregates data from all modules."""
from datetime import datetime, timezone, timedelta
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import CurrentUser
from app.models.trade import Trade
from app.models.journal import JournalEntry
from app.models.signal import Signal
from app.models.strategy import Strategy, Playbook
from app.models.risk import RiskSettings, RiskEvent
from app.models.backtest import BacktestResult
from app.enums import TradeStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Comprehensive dashboard summary for the current user.

    Returns:
    - **portfolio**: open position count, total realized P&L
    - **trades_summary**: 30-day totals, win rate, avg R-multiple
    - **signals_24h**: per-status signal counts from the last 24 hours
    - **strategies**: total and active-auto strategy counts
    - **risk**: circuit_breaker status, risk events in last 24h
    - **journal**: total entries and entries in last 7 days
    - **backtests**: total completed
    - **recent_signals**: last 5 signals
    - **recent_trades**: last 5 trades
    """
    uid = current_user.id
    now = datetime.now(tz=timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    # ── Portfolio ─────────────────────────────────────────────────────────────

    # Open position count + total realized P&L in one query
    portfolio_result = await db.execute(
        select(
            func.count(case((Trade.status == TradeStatus.open.value, 1))).label("open_positions"),
            func.coalesce(
                func.sum(
                    case((Trade.status == TradeStatus.closed.value, Trade.pnl), else_=None)
                ),
                0,
            ).label("total_realized_pnl"),
        ).where(Trade.user_id == uid)
    )
    portfolio_row = portfolio_result.one()
    open_positions = portfolio_row.open_positions
    total_realized_pnl = round(float(portfolio_row.total_realized_pnl), 2)

    # 30-day trade stats: all in SQL
    stats_result = await db.execute(
        select(
            func.count().label("total"),
            func.count(case((Trade.status == TradeStatus.closed.value, 1))).label("closed"),
            func.count(
                case((
                    and_(
                        Trade.status == TradeStatus.closed.value,
                        Trade.pnl > 0,
                    ),
                    1,
                ))
            ).label("winners"),
            func.avg(
                case((Trade.status == TradeStatus.closed.value, Trade.r_multiple), else_=None)
            ).label("avg_r"),
        ).where(Trade.user_id == uid, Trade.created_at >= since_30d)
    )
    stats = stats_result.one()
    win_rate_30d = (
        round(stats.winners / stats.closed * 100, 1) if stats.closed else None
    )
    avg_r_30d = round(float(stats.avg_r), 2) if stats.avg_r is not None else None

    # Recent trades (5)
    recent_trades_result = await db.execute(
        select(Trade)
        .where(Trade.user_id == uid)
        .order_by(Trade.created_at.desc())
        .limit(5)
    )
    recent_trades = recent_trades_result.scalars().all()

    # ── Signals ───────────────────────────────────────────────────────────────

    counts_result = await db.execute(
        select(Signal.status, func.count().label("n"))
        .where(Signal.user_id == uid, Signal.created_at >= since_24h)
        .group_by(Signal.status)
    )
    signal_counts = {row.status: row.n for row in counts_result}

    recent_signals_result = await db.execute(
        select(Signal)
        .where(Signal.user_id == uid)
        .order_by(Signal.created_at.desc())
        .limit(5)
    )
    recent_signals = recent_signals_result.scalars().all()

    # ── Strategies (total + active-auto in one JOIN query) ────────────────────

    strats_result = await db.execute(
        select(
            func.count().label("total"),
            func.count(
                case((
                    and_(
                        Strategy.automation_mode != "disabled",
                        Strategy.is_active.is_(True),
                    ),
                    1,
                ))
            ).label("active_auto"),
        ).select_from(Strategy).join(Playbook, Strategy.playbook_id == Playbook.id)
        .where(Playbook.user_id == uid)
    )
    strats_row = strats_result.one()

    # ── Risk ──────────────────────────────────────────────────────────────────

    risk_result = await db.execute(
        select(RiskSettings).where(RiskSettings.user_id == uid)
    )
    risk_settings = risk_result.scalar_one_or_none()

    risk_events_result = await db.execute(
        select(func.count()).select_from(RiskEvent).where(
            RiskEvent.user_id == uid,
            RiskEvent.triggered_at >= since_24h,
        )
    )
    risk_events_24h = risk_events_result.scalar_one()

    # ── Journal (total + 7-day in one query) ──────────────────────────────────

    journal_result = await db.execute(
        select(
            func.count().label("total"),
            func.count(
                case((JournalEntry.created_at >= since_7d, 1))
            ).label("last_7d"),
        ).where(JournalEntry.user_id == uid)
    )
    journal_row = journal_result.one()

    # ── Backtests ─────────────────────────────────────────────────────────────

    backtests_result = await db.execute(
        select(func.count()).select_from(BacktestResult).where(
            BacktestResult.user_id == uid,
            BacktestResult.status == "complete",
        )
    )
    total_backtests = backtests_result.scalar_one()

    return {
        "portfolio": {
            "open_positions": open_positions,
            "total_realized_pnl": total_realized_pnl,
            "unrealized_pnl": None,           # Requires live prices — not yet implemented
            "unrealized_pnl_available": False,
        },
        "trades_summary": {
            "total_30d": stats.total,
            "closed_30d": stats.closed,
            "win_rate_30d_pct": win_rate_30d,
            "avg_r_multiple_30d": avg_r_30d,
        },
        "signals_24h": {
            "pending": signal_counts.get("pending", 0),
            "executed": signal_counts.get("executed", 0),
            "rejected": signal_counts.get("rejected", 0),
            "expired": signal_counts.get("expired", 0),
        },
        "strategies": {
            "total": strats_row.total,
            "active_auto": strats_row.active_auto,
        },
        "risk": {
            "circuit_breaker_active": risk_settings.circuit_breaker_active if risk_settings else False,
            "risk_events_24h": risk_events_24h,
        },
        "journal": {
            "total_entries": journal_row.total,
            "entries_last_7d": journal_row.last_7d,
        },
        "backtests": {
            "total_completed": total_backtests,
        },
        "recent_signals": [
            {
                "id": str(s.id),
                "symbol": s.symbol,
                "pattern_name": s.pattern_name,
                "direction": s.direction,
                "status": s.status,
                "confidence_score": float(s.confidence_score),
                "created_at": s.created_at.isoformat(),
            }
            for s in recent_signals
        ],
        "recent_trades": [
            {
                "id": str(t.id),
                "symbol": t.symbol,
                "side": t.side,
                "status": t.status,
                "pnl": float(t.pnl) if t.pnl is not None else None,
                "created_at": t.created_at.isoformat(),
            }
            for t in recent_trades
        ],
    }
