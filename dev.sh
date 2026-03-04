#!/usr/bin/env bash
# dev.sh — Start the Trading app locally with demo data, no credentials required.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
ENV_FILE="$BACKEND_DIR/.env"

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
info()    { echo -e "${CYAN}[dev]${RESET} $*"; }
success() { echo -e "${GREEN}[dev]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[dev]${RESET} $*"; }

# ── Prerequisites ─────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  echo "Docker is not installed. Install it from https://docs.docker.com/get-docker/"
  exit 1
fi
if ! docker compose version &>/dev/null; then
  echo "Docker Compose plugin not found. Update Docker Desktop or install the plugin."
  exit 1
fi

# ── Generate .env if missing ──────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  info "Generating $ENV_FILE with random dev keys..."
  SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null \
    || openssl rand -base64 32 | tr -d '\n/+=' | head -c 44)
  ENCRYPTION_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(24)[:32])" 2>/dev/null \
    || openssl rand -base64 24 | tr -d '\n/+=' | head -c 32)

  cat > "$ENV_FILE" <<EOF
# Auto-generated dev environment — do NOT use in production
DATABASE_URL=postgresql+asyncpg://trading:trading_secret@localhost:5432/trading_db
SYNC_DATABASE_URL=postgresql://trading:trading_secret@localhost:5432/trading_db
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=${SECRET_KEY}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
ENVIRONMENT=development
DEBUG=true
QUESTRADE_CLIENT_ID=
EOF
  success ".env created"
else
  info "Using existing $ENV_FILE"
fi

# ── Stop any previous run ─────────────────────────────────────────────────────
info "Stopping any previous containers..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" down --remove-orphans 2>/dev/null || true

# ── Start services ────────────────────────────────────────────────────────────
info "Building and starting services (this may take a minute on first run)..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up --build -d

# ── Wait for backend to be healthy ────────────────────────────────────────────
info "Waiting for backend to be ready..."
MAX_WAIT=60
WAITED=0
until curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; do
  if [[ $WAITED -ge $MAX_WAIT ]]; then
    echo "Backend did not become healthy within ${MAX_WAIT}s."
    echo "Check logs: docker compose logs backend"
    exit 1
  fi
  sleep 2
  WAITED=$((WAITED + 2))
done
success "Backend is up"

# ── Run migrations ────────────────────────────────────────────────────────────
info "Running database migrations..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" exec -T backend \
  alembic upgrade head
success "Migrations complete"

# ── Seed demo data ────────────────────────────────────────────────────────────
info "Seeding demo data..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" exec -T backend \
  python3 - <<'PYSEED'
import asyncio, uuid, json
from datetime import datetime, timezone, timedelta
from decimal import Decimal

async def seed():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.config import settings
    from app.models.user import User
    from app.models.trade import Trade
    from app.models.strategy import Playbook, Strategy
    from app.models.journal import JournalEntry
    from app.models.signal import Signal
    from app.models.risk import RiskSettings
    from app.models.backtest import BacktestResult
    from app.auth.service import hash_password

    engine = create_async_engine(settings.database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # Check if demo user already exists
        from sqlalchemy import select
        existing = await db.execute(select(User).where(User.email == "demo@example.com"))
        if existing.scalar_one_or_none():
            print("Demo data already exists — skipping seed.")
            return

        now = datetime.now(tz=timezone.utc)

        # ── Demo user ─────────────────────────────────────────────────────────
        user = User(
            email="demo@example.com",
            password_hash=hash_password("Demo1234!"),
        )
        db.add(user)
        await db.flush()
        uid = user.id

        # ── Risk settings ─────────────────────────────────────────────────────
        db.add(RiskSettings(user_id=uid))

        # ── Playbook + strategies ─────────────────────────────────────────────
        pb = Playbook(
            user_id=uid,
            name="Momentum Breakouts",
            description="Price-action setups at key levels with volume confirmation",
            theory="Trade in the direction of the dominant order flow. Wait for range compression then breakout with volume.",
            context_rules=["Market above 20-day MA", "VIX < 25", "Sector leading"],
            trigger_rules=["Price breaks consolidation high", "Volume > 2× average", "Close near high"],
            management_rules={"stop": "Below consolidation low", "target": "2–3× risk", "trail": "On 2× R"},
        )
        db.add(pb)
        await db.flush()

        strat1 = Strategy(
            playbook_id=pb.id, name="SPY Breakout",
            automation_mode="semi_auto", is_active=True,
            config={"min_consolidation_bars": 10, "volume_multiplier": 2.0},
            watchlist=["SPY", "QQQ", "IWM"],
        )
        strat2 = Strategy(
            playbook_id=pb.id, name="Large-Cap Momentum",
            automation_mode="disabled", is_active=True,
            config={"min_consolidation_bars": 15, "volume_multiplier": 1.8},
            watchlist=["AAPL", "MSFT", "NVDA", "AMZN"],
        )
        db.add_all([strat1, strat2])
        await db.flush()

        # ── Trades ────────────────────────────────────────────────────────────
        trades_data = [
            ("SPY",  "stock", "long",  50,  Decimal("481.20"), Decimal("487.50"), Decimal("2.52"),  Decimal("0.52"),  "closed", -15),
            ("QQQ",  "etf",   "long",  30,  Decimal("402.00"), Decimal("409.80"), Decimal("7.50"),  Decimal("1.87"),  "closed", -12),
            ("AAPL", "stock", "long",  25,  Decimal("188.40"), Decimal("182.10"), Decimal("-6.30"), Decimal("-1.26"), "closed", -8),
            ("NVDA", "stock", "long",  10,  Decimal("875.00"), Decimal("901.25"), Decimal("8.75"),  Decimal("1.75"),  "closed", -3),
            ("MSFT", "stock", "long",  20,  Decimal("415.60"), None,              None,             None,             "open",   -1),
            ("IWM",  "etf",   "short", 40,  Decimal("197.30"), Decimal("193.20"), Decimal("4.05"),  Decimal("0.81"),  "closed", -5),
        ]
        trade_objs = []
        for sym, itype, side, qty, entry, exit_p, pnl, pnl_pct, tstat, days_ago in trades_data:
            entry_time = now + timedelta(days=days_ago)
            t = Trade(
                user_id=uid,
                strategy_id=strat1.id,
                symbol=sym,
                instrument_type=itype,
                side=side,
                quantity=Decimal(str(qty)),
                entry_price=entry,
                exit_price=exit_p,
                entry_time=entry_time,
                exit_time=(entry_time + timedelta(hours=6)) if exit_p else None,
                status=tstat,
                pnl=pnl,
                pnl_pct=pnl_pct,
                r_multiple=Decimal("1.85") if pnl and float(pnl) > 0 else (Decimal("-1.0") if pnl and float(pnl) < 0 else None),
                stop_loss=entry * Decimal("0.985"),
                take_profit=entry * Decimal("1.025") if exit_p is None else exit_p,
                notes=f"Clean {sym} setup at key level.",
                created_at=entry_time,
            )
            db.add(t)
            trade_objs.append(t)
        await db.flush()

        # ── Journal entries ───────────────────────────────────────────────────
        journal_data = [
            (trade_objs[0], "Strong SPY breakout", ["breakout", "trend"], "Textbook setup. Volume confirmed the move. Held for the full target.", 8, 9, True, "Patience with entries pays off"),
            (trade_objs[1], "QQQ follow-through", ["momentum", "etf"],   "Nice continuation after morning consolidation.",                       7, 8, True, "Set alerts earlier next time"),
            (trade_objs[2], "AAPL reversal — stopped out", ["reversal", "loss"], "Entered too early before confirmation. Stop was in the right place.", 6, 5, False, "Wait for candle close before entry"),
            (trade_objs[3], "NVDA earnings momentum", ["earnings", "momentum"], "Huge move. Should have sized up — setup was A+.",                  9, 9, True,  "Size up on high-conviction setups"),
        ]
        for trade, title, tags, notes, conf, qual, followed, lesson in journal_data:
            db.add(JournalEntry(
                user_id=uid,
                trade_id=trade.id,
                entry_date=trade.entry_time.date(),
                title=title,
                tags=tags,
                notes=notes,
                confidence_before=conf,
                execution_quality=qual,
                followed_playbook=followed,
                lessons_learned=lesson,
                context_abbreviation="TU" if followed else "TC",
                trigger_abbreviation="BO",
                management_abbreviation="T2",
                created_at=trade.entry_time,
                updated_at=trade.entry_time,
            ))

        # ── Signals ───────────────────────────────────────────────────────────
        signals_data = [
            ("SPY",  "breakout",     "bullish", 82.4, "executed", -1,   "Auto-executed by full_auto scanner."),
            ("QQQ",  "breakout",     "bullish", 74.1, "executed", -3,   "Confirmed and executed by user."),
            ("AAPL", "pin_bar",      "bullish", 61.8, "rejected", -2,   None),
            ("NVDA", "volume_spike", "bullish", 90.3, "executed", -1,   "Confirmed and executed by user."),
            ("IWM",  "breakout",     "bearish", 68.5, "pending",   0,   None),
            ("MSFT", "vwap_bounce",  "bullish", 55.2, "pending",   0,   None),
        ]
        for sym, pat, direction, conf, sstat, days_ago, enote in signals_data:
            created = now + timedelta(days=days_ago, hours=-2)
            db.add(Signal(
                user_id=uid,
                strategy_id=strat1.id,
                symbol=sym,
                pattern_name=pat,
                direction=direction,
                confidence_score=Decimal(str(conf)),
                automation_mode="semi_auto",
                status=sstat,
                execution_note=enote,
                pattern_meta={"wick_ratio": 3.2} if pat == "pin_bar" else {"breakout_price": 482.5},
                expires_at=now + timedelta(hours=1) if sstat == "pending" else None,
                resolved_at=created + timedelta(hours=1) if sstat in ("executed", "rejected") else None,
                created_at=created,
            ))

        # ── Backtest results ──────────────────────────────────────────────────
        db.add(BacktestResult(
            user_id=uid,
            strategy_id=strat1.id,
            status="complete",
            config={
                "symbol": "SPY", "pattern_name": "breakout",
                "stop_loss_pct": 1.5, "take_profit_pct": 3.0,
                "initial_capital": 50000,
            },
            results={
                "total_trades": 47, "winning_trades": 29, "losing_trades": 18,
                "win_rate": 61.7, "total_return_pct": 18.4,
                "max_drawdown_pct": 6.2, "sharpe_ratio": 1.43,
                "profit_factor": 2.1, "avg_r_multiple": 1.32,
                "final_capital": 59200,
            },
            completed_at=now - timedelta(days=2),
            created_at=now - timedelta(days=2),
        ))

        await db.commit()
        print("Demo data seeded successfully.")

asyncio.run(seed())
PYSEED

success "Demo data seeded"

# ── Print summary ─────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}  Trading App is running!${RESET}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  ${CYAN}Frontend${RESET}      http://localhost:3000"
echo -e "  ${CYAN}API docs${RESET}      http://localhost:8000/docs"
echo ""
echo -e "  ${CYAN}Demo login${RESET}"
echo -e "    Email:    demo@example.com"
echo -e "    Password: Demo1234!"
echo ""
echo -e "  ${CYAN}Demo data includes:${RESET}"
echo -e "    • 6 trades (5 closed, 1 open) across SPY, QQQ, AAPL, NVDA, MSFT, IWM"
echo -e "    • 4 journal entries with notes and lessons"
echo -e "    • 6 signals (2 pending, 3 executed, 1 rejected)"
echo -e "    • 1 completed backtest (SPY breakout, 47 trades, 61.7% win rate)"
echo -e "    • 1 playbook with 2 strategies"
echo ""
echo -e "  ${YELLOW}To stop:${RESET}  docker compose down"
echo -e "  ${YELLOW}Logs:${RESET}     docker compose logs -f backend"
echo ""
