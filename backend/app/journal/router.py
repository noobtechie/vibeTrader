"""Trading Journal API — entries, analytics, CSV export."""
import csv
import io
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func, cast, String as SAString
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.dependencies import CurrentUser
from app.models.journal import JournalEntry
from app.models.trade import Trade


_FORMULA_START = re.compile(r'^[=+\-@\t\r]')


def _csv_safe(value: str) -> str:
    """Prefix spreadsheet formula characters to prevent CSV injection."""
    if value and _FORMULA_START.match(value):
        return "'" + value
    return value

router = APIRouter(prefix="/journal", tags=["journal"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class JournalEntryCreate(BaseModel):
    entry_date: Optional[date] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    screenshots: Optional[list[str]] = None
    trade_id: Optional[uuid.UUID] = None
    context_abbreviation: Optional[str] = None
    trigger_abbreviation: Optional[str] = None
    management_abbreviation: Optional[str] = None
    sizing_tier: Optional[str] = None
    confidence_before: Optional[int] = None
    execution_quality: Optional[int] = None
    followed_playbook: Optional[bool] = None
    lessons_learned: Optional[str] = None

    @field_validator("confidence_before", "execution_quality", mode="before")
    @classmethod
    def rating_range(cls, v):
        if v is not None and not (1 <= int(v) <= 10):
            raise ValueError("Rating must be between 1 and 10")
        return v


class JournalEntryUpdate(JournalEntryCreate):
    pass


def _entry_dict(e: JournalEntry) -> dict:
    return {
        "id": str(e.id),
        "user_id": str(e.user_id),
        "trade_id": str(e.trade_id) if e.trade_id else None,
        "entry_date": e.entry_date.isoformat() if e.entry_date else None,
        "title": e.title,
        "notes": e.notes,
        "tags": e.tags,
        "screenshots": e.screenshots,
        "context_abbreviation": e.context_abbreviation,
        "trigger_abbreviation": e.trigger_abbreviation,
        "management_abbreviation": e.management_abbreviation,
        "sizing_tier": e.sizing_tier,
        "confidence_before": e.confidence_before,
        "execution_quality": e.execution_quality,
        "followed_playbook": e.followed_playbook,
        "lessons_learned": e.lessons_learned,
        "created_at": e.created_at.isoformat(),
        "updated_at": e.updated_at.isoformat(),
    }


async def _get_entry_or_404(
    db: AsyncSession, entry_id: uuid.UUID, user_id: uuid.UUID
) -> JournalEntry:
    result = await db.execute(
        select(JournalEntry).where(
            JournalEntry.id == entry_id,
            JournalEntry.user_id == user_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return entry


# ─── CRUD endpoints ───────────────────────────────────────────────────────────

@router.get("/entries")
async def list_entries(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    tag: Optional[str] = Query(None),
    trade_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    base_filter = [JournalEntry.user_id == current_user.id]
    if from_date:
        base_filter.append(JournalEntry.entry_date >= from_date)
    if to_date:
        base_filter.append(JournalEntry.entry_date <= to_date)
    if trade_id:
        base_filter.append(JournalEntry.trade_id == trade_id)
    if tag:
        # JSON stored as text in SQLite; quoting both sides prevents partial-tag matches
        base_filter.append(cast(JournalEntry.tags, SAString).contains(f'"{tag}"'))

    total_result = await db.execute(
        select(func.count()).select_from(JournalEntry).where(*base_filter)
    )
    total = total_result.scalar_one()

    query = (
        select(JournalEntry)
        .where(*base_filter)
        .order_by(JournalEntry.entry_date.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    entries = result.scalars().all()

    return {"entries": [_entry_dict(e) for e in entries], "count": len(entries), "total": total}


@router.post("/entries", status_code=status.HTTP_201_CREATED)
async def create_entry(
    body: JournalEntryCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Validate trade_id belongs to this user
    if body.trade_id:
        trade_result = await db.execute(
            select(Trade).where(
                Trade.id == body.trade_id,
                Trade.user_id == current_user.id,
            )
        )
        if not trade_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Trade not found")

    data = body.model_dump(exclude_unset=True)
    entry = JournalEntry(
        user_id=current_user.id,
        entry_date=data.pop("entry_date", None) or date.today(),
        **data,
    )
    db.add(entry)
    await db.flush()
    return {"entry": _entry_dict(entry)}


@router.post("/entries/from-trade/{trade_id}", status_code=status.HTTP_201_CREATED)
async def create_entry_from_trade(
    trade_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Auto-create a journal entry pre-populated from a trade record."""
    trade_result = await db.execute(
        select(Trade).where(Trade.id == trade_id, Trade.user_id == current_user.id)
    )
    trade = trade_result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    # Idempotency: return 409 if a journal entry already exists for this trade
    existing = await db.execute(
        select(JournalEntry).where(
            JournalEntry.trade_id == trade_id,
            JournalEntry.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Journal entry already exists for this trade")

    entry_date = trade.entry_time.date() if trade.entry_time else date.today()
    title = f"{trade.side.upper()} {trade.symbol}"
    entry = JournalEntry(
        user_id=current_user.id,
        trade_id=trade.id,
        entry_date=entry_date,
        title=title,
    )
    db.add(entry)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Journal entry already exists for this trade")
    return {"entry": _entry_dict(entry)}


@router.get("/entries/{entry_id}")
async def get_entry(
    entry_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    entry = await _get_entry_or_404(db, entry_id, current_user.id)
    return {"entry": _entry_dict(entry)}


@router.put("/entries/{entry_id}")
async def update_entry(
    entry_id: uuid.UUID,
    body: JournalEntryUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    entry = await _get_entry_or_404(db, entry_id, current_user.id)
    updates = body.model_dump(exclude_unset=True)

    # If trade_id is being set, verify ownership and uniqueness
    if "trade_id" in updates and updates["trade_id"] is not None:
        trade_check = await db.execute(
            select(Trade).where(
                Trade.id == updates["trade_id"],
                Trade.user_id == current_user.id,
            )
        )
        if not trade_check.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Trade not found")

        # Ensure no other journal entry already links to this trade
        dup_check = await db.execute(
            select(JournalEntry).where(
                JournalEntry.trade_id == updates["trade_id"],
                JournalEntry.id != entry_id,
            )
        )
        if dup_check.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A journal entry already exists for this trade")

    for field, value in updates.items():
        setattr(entry, field, value)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="A journal entry already exists for this trade")
    return {"entry": _entry_dict(entry)}


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: uuid.UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    entry = await _get_entry_or_404(db, entry_id, current_user.id)
    await db.delete(entry)
    await db.flush()


# ─── Analytics ────────────────────────────────────────────────────────────────

@router.get("/analytics/summary")
async def get_analytics_summary(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
):
    """Win rate, avg R-multiple, profit factor, and expectancy for closed trades."""
    query = select(Trade).where(
        Trade.user_id == current_user.id,
        Trade.status == "closed",
        Trade.pnl.is_not(None),
    )
    if from_date:
        query = query.where(Trade.entry_time >= from_date)
    if to_date:
        query = query.where(Trade.entry_time < (to_date + timedelta(days=1)))

    result = await db.execute(query)
    trades = result.scalars().all()

    if not trades:
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "win_rate": 0.0, "avg_pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "profit_factor": None, "expectancy": 0.0,
            "avg_r_multiple": None, "total_pnl": 0.0,
        }

    pnls = [float(t.pnl) for t in trades]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p < 0]

    total = len(trades)
    win_count = len(winners)
    loss_count = len(losers)
    win_rate = win_count / total
    avg_win = sum(winners) / len(winners) if winners else 0.0
    avg_loss = sum(losers) / len(losers) if losers else 0.0
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    profit_factor = gross_profit / gross_loss if gross_loss else None
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    r_multiples = [float(t.r_multiple) for t in trades if t.r_multiple is not None]
    avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else None

    return {
        "total_trades": total,
        "winning_trades": win_count,
        "losing_trades": loss_count,
        "win_rate": round(win_rate, 4),
        "avg_pnl": round(sum(pnls) / total, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 4) if profit_factor else None,
        "expectancy": round(expectancy, 2),
        "avg_r_multiple": round(avg_r, 4) if avg_r is not None else None,
        "total_pnl": round(sum(pnls), 2),
    }


@router.get("/analytics/by-day-of-week")
async def analytics_by_day_of_week(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """P&L and win rate grouped by day of week (0=Mon … 6=Sun)."""
    result = await db.execute(
        select(Trade).where(
            Trade.user_id == current_user.id,
            Trade.status == "closed",
            Trade.pnl.is_not(None),
            Trade.entry_time.is_not(None),
        )
    )
    trades = result.scalars().all()

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    buckets: dict[int, list[float]] = {i: [] for i in range(7)}
    for t in trades:
        buckets[t.entry_time.weekday()].append(float(t.pnl))

    return {
        "by_day": [
            {
                "day": day_names[i],
                "total_trades": len(pnls),
                "total_pnl": round(sum(pnls), 2) if pnls else 0.0,
                "win_rate": round(len([p for p in pnls if p > 0]) / len(pnls), 4) if pnls else 0.0,
            }
            for i, pnls in buckets.items()
        ]
    }


@router.get("/analytics/by-time-of-day")
async def analytics_by_time_of_day(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """P&L and win rate grouped by entry hour (0-23, UTC as stored)."""
    result = await db.execute(
        select(Trade).where(
            Trade.user_id == current_user.id,
            Trade.status == "closed",
            Trade.pnl.is_not(None),
            Trade.entry_time.is_not(None),
        )
    )
    trades = result.scalars().all()

    buckets: dict[int, list[float]] = {h: [] for h in range(24)}
    for t in trades:
        buckets[t.entry_time.hour].append(float(t.pnl))

    return {
        "by_hour": [
            {
                "hour": h,
                "total_trades": len(pnls),
                "total_pnl": round(sum(pnls), 2) if pnls else 0.0,
                "win_rate": round(len([p for p in pnls if p > 0]) / len(pnls), 4) if pnls else 0.0,
            }
            for h, pnls in buckets.items()
        ]
    }


@router.get("/analytics/by-strategy")
async def analytics_by_strategy(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """P&L metrics grouped by strategy_id."""
    result = await db.execute(
        select(Trade).where(
            Trade.user_id == current_user.id,
            Trade.status == "closed",
            Trade.pnl.is_not(None),
        )
    )
    trades = result.scalars().all()

    buckets: dict[str, list[float]] = {}
    for t in trades:
        key = str(t.strategy_id) if t.strategy_id else "no_strategy"
        buckets.setdefault(key, []).append(float(t.pnl))

    rows = []
    for strat_id, pnls in buckets.items():
        wins = [p for p in pnls if p > 0]
        rows.append({
            "strategy_id": strat_id,
            "total_trades": len(pnls),
            "total_pnl": round(sum(pnls), 2),
            "win_rate": round(len(wins) / len(pnls), 4) if pnls else 0.0,
            "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        })

    return {"by_strategy": sorted(rows, key=lambda r: r["total_pnl"], reverse=True)}


# ─── CSV export ───────────────────────────────────────────────────────────────

@router.get("/export/csv")
async def export_csv(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
):
    """Export all closed trades and journal notes as a CSV file."""
    trades_query = select(Trade).where(
        Trade.user_id == current_user.id,
        Trade.status == "closed",
    )
    if from_date:
        trades_query = trades_query.where(Trade.entry_time >= from_date)
    if to_date:
        trades_query = trades_query.where(Trade.entry_time < (to_date + timedelta(days=1)))

    trades_result = await db.execute(trades_query)
    trades = trades_result.scalars().all()

    # Build trade_id → journal entry map
    trade_ids = [t.id for t in trades]
    journal_map: dict = {}
    if trade_ids:
        j_result = await db.execute(
            select(JournalEntry).where(
                JournalEntry.user_id == current_user.id,
                JournalEntry.trade_id.in_(trade_ids),
            )
        )
        for j in j_result.scalars().all():
            journal_map[j.trade_id] = j

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "trade_id", "symbol", "instrument_type", "side", "quantity",
        "entry_price", "exit_price", "stop_loss", "entry_time", "exit_time",
        "pnl", "pnl_pct", "r_multiple", "commission", "strategy_id",
        "journal_title", "journal_notes", "tags", "context", "trigger",
        "management", "sizing_tier", "followed_playbook", "lessons_learned",
    ])

    for t in trades:
        j = journal_map.get(t.id)
        writer.writerow([
            str(t.id), _csv_safe(t.symbol), _csv_safe(t.instrument_type), _csv_safe(t.side), t.quantity,
            float(t.entry_price) if t.entry_price else "",
            float(t.exit_price) if t.exit_price else "",
            float(t.stop_loss) if t.stop_loss else "",
            t.entry_time.isoformat() if t.entry_time else "",
            t.exit_time.isoformat() if t.exit_time else "",
            float(t.pnl) if t.pnl is not None else "",
            float(t.pnl_pct) if t.pnl_pct is not None else "",
            float(t.r_multiple) if t.r_multiple is not None else "",
            float(t.commission),
            str(t.strategy_id) if t.strategy_id else "",
            _csv_safe(j.title) if j and j.title else "",
            _csv_safe(j.notes) if j and j.notes else "",
            ",".join(_csv_safe(t) for t in j.tags) if j and j.tags else "",
            _csv_safe(j.context_abbreviation) if j and j.context_abbreviation else "",
            _csv_safe(j.trigger_abbreviation) if j and j.trigger_abbreviation else "",
            _csv_safe(j.management_abbreviation) if j and j.management_abbreviation else "",
            _csv_safe(j.sizing_tier) if j and j.sizing_tier else "",
            j.followed_playbook if j else "",
            _csv_safe(j.lessons_learned) if j and j.lessons_learned else "",
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trades.csv"},
    )
