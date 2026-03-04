# CLAUDE.md — Trading Automation Platform

## Project Overview

Personal trading automation platform. Backend: FastAPI + SQLAlchemy 2.0 async + PostgreSQL/TimescaleDB. Frontend: Next.js 14+ (TypeScript).

Working directory for backend work: `backend/`
Run commands from: `/home/sounak/work/Trading/backend`

## Commands

```bash
# Tests (always run from backend/)
python3.12 -m pytest -q                          # full suite
python3.12 -m pytest tests/test_automation.py -v  # single file

# Linting
ruff check app/
black --check app/

# API server (dev)
uvicorn app.main:app --reload

# All services
docker compose up --build
```

## Architecture

```
app/
├── main.py              # Router registration, CORS, WebSocket endpoint
├── config.py            # Pydantic-settings (Settings class)
├── database.py          # AsyncSession factory, Base
├── enums.py             # ALL shared enums (AutomationMode, TradeStatus, etc.)
├── auth/                # JWT auth — router.py, service.py, dependencies.py
├── brokerage/           # Questrade OAuth2 + streaming — base.py ABC + questrade/
├── strategies/          # Playbook CRUD + pattern detectors in patterns/
├── journal/             # Journal entries, analytics, CSV export
├── backtesting/         # engine.py (pure function), router.py, tasks.py (Celery)
├── automation/          # scanner.py (pure function), router.py (signal CRUD)
├── risk/                # router.py + service.py (risk validation)
├── data_sources/        # base.py (BaseDataSource ABC), router.py (config CRUD)
├── dashboard/           # Aggregated dashboard — SQL aggregation only
├── websocket/           # manager.py (Redis pub/sub), events.py
└── models/              # SQLAlchemy ORM models (one file per domain)
```

## Key Patterns & Rules

### DateTime — always timezone-aware
All ORM datetime columns use `DateTime(timezone=True)` with:
```python
default=lambda: datetime.now(timezone.utc)
onupdate=lambda: datetime.now(timezone.utc)
```
Never use `datetime.utcnow` — it is deprecated in Python 3.12 and returns a naive datetime.
SQLite (test DB) strips timezone info. When comparing stored datetimes, guard with:
```python
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
```

### Pattern detectors
- `detect_pin_bar(opens, highs, lows, closes, **params)` — unique: `opens` is first arg
- All others: `detect_X(highs, lows, closes, ...)` or with `volumes`
- Use `Decimal` arrays when calling detectors (precision), `float` for simulation loops

### Parameter validation
Both `scanner.py` and `backtesting/engine.py` define `PATTERN_PARAM_KEYS` allowlists.
`ScanRequest` enforces `params_must_be_numeric` — all pattern param values must be `int` or `float`.
Unknown keys raise `ValueError` → 422 in the router.

### Strategy ownership
Strategies do not have a direct `user_id`. Always join through Playbook:
```python
select(Strategy).join(Playbook, Strategy.playbook_id == Playbook.id).where(Playbook.user_id == uid)
```

### Signal lifecycle
`SIGNAL_STATUSES = {"pending", "rejected", "executed", "expired"}` — no "confirmed" state.
`confirm_signal`: `pending → executed` directly.

### Pydantic v2 validation
Use `@field_validator` (not `model_post_init`) for field validation — produces located errors.
Use `@model_validator(mode="after")` for cross-field invariants (e.g., OHLC integrity).

### Dashboard SQL
All aggregations must stay in SQL — no unbounded Python-side fetches.
Use `func.sum()`, `func.count()`, `case()` for conditional aggregation.
Consolidate paired queries on the same table into one query where possible.

### Enums
Add new enums to `app/enums.py` only. Models import from there. Never define enums inline in model files.

### Auth dependency
`CurrentUser` dependency (from `app.auth.dependencies`) returns the authenticated `User` ORM object.
All user-scoped queries filter by `current_user.id`.

## Test Setup

Tests use SQLite (aiosqlite) via a shared in-memory database per test session.
Conftest fixtures: `client` (AsyncClient), `auth_headers` (dict with Bearer token), `db` (AsyncSession).
No mocking of the DB layer — tests hit a real (in-memory) database.

## Models

| Model | File | Key notes |
|---|---|---|
| `User` | `models/user.py` | Argon2 password hashing |
| `Trade`, `Order` | `models/trade.py` | `Trade.created_at` is `DateTime(timezone=True)` |
| `Playbook`, `Strategy` | `models/strategy.py` | Strategy has no direct `user_id` — use Playbook join |
| `JournalEntry` | `models/journal.py` | `UniqueConstraint("trade_id")` — one entry per trade |
| `Signal` | `models/signal.py` | `Index("ix_signals_user_status", "user_id", "status")` |
| `BacktestResult` | `models/backtest.py` | status: `"complete"` or `"error"` |
| `RiskSettings` | `models/risk.py` | One per user (`unique=True` on `user_id`) |
| `DataSourceConfig` | `models/market_data.py` | `is_default` is exclusive per user |

## Adding a New Data Source

1. Create `app/data_sources/<name>.py`
2. Subclass `BaseDataSource` from `app/data_sources/base.py`
3. Define `source_type: str = "<name>"` (must match a `DataSourceType` enum value)
4. Implement `fetch_candles()` and `search_symbols()`
5. Add the new value to `DataSourceType` in `app/enums.py`

## Adding a New Pattern

1. Create `app/strategies/patterns/<name>.py` with a `detect_<name>()` function
2. Add to `VALID_PATTERNS` and `PATTERN_PARAM_KEYS` in both `app/automation/scanner.py` and `app/backtesting/engine.py`
3. Add the dispatch branch in `scanner.py::scan()` and `engine.py::_detect_signal()`

## Environment

Python 3.12+. Key dependencies: fastapi 0.115, sqlalchemy 2.0, pydantic 2.10, celery 5.4.
Test runner: `pytest` with `pytest-asyncio`. Coverage target: aim for >70% on new modules.
