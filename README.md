# Trading Automation Platform

A personal trading automation platform with Questrade brokerage integration. Supports strategy playbooks, risk management, trade journaling, backtesting, and automated pattern scanning.

## Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python 3.12+, async) |
| Database | PostgreSQL 16 + TimescaleDB |
| ORM | SQLAlchemy 2.0 + Alembic |
| Task Queue | Celery + Redis |
| Real-time | WebSockets (FastAPI + Redis pub/sub) |
| Frontend | Next.js 14+ (TypeScript, Tailwind CSS, shadcn/ui) |
| Auth | JWT (app) + OAuth2 (Questrade) |

## Quick Start

```bash
# Copy and edit environment config
cp backend/.env.example backend/.env   # set SECRET_KEY, ENCRYPTION_KEY, Questrade credentials

# Start all services
docker compose up --build

# API:      http://localhost:8000
# Docs:     http://localhost:8000/docs
# Frontend: http://localhost:3000
```

## Project Structure

```
Trading/
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── enums.py             # Shared enum definitions
│   │   ├── auth/                # JWT registration & login
│   │   ├── brokerage/           # Questrade OAuth2 + API client
│   │   ├── strategies/          # Playbooks + pattern detectors
│   │   ├── journal/             # Trade journal + analytics + CSV export
│   │   ├── backtesting/         # Backtest engine + Celery tasks
│   │   ├── automation/          # Scanner + signal management
│   │   ├── risk/                # Risk limits + circuit breaker
│   │   ├── data_sources/        # BaseDataSource ABC + config CRUD
│   │   ├── dashboard/           # Aggregated overview endpoint
│   │   ├── websocket/           # WS manager + Redis pub/sub
│   │   └── models/              # SQLAlchemy ORM models
│   ├── alembic/                 # Database migrations
│   └── tests/                   # pytest test suite (184 tests)
└── frontend/
    └── src/
        └── app/                 # Next.js App Router pages
```

## API Modules

| Prefix | Module |
|---|---|
| `/api/v1/auth` | Register, login, JWT tokens |
| `/api/v1/brokerage` | Questrade connect, accounts, positions, quotes |
| `/api/v1/strategies` | Playbooks and strategies CRUD |
| `/api/v1/risk` | Risk settings, events, circuit breaker |
| `/api/v1/journal` | Entries, analytics, CSV export |
| `/api/v1/backtest` | Run backtests, view results |
| `/api/v1/automation` | Scan patterns, manage signals, dashboard |
| `/api/v1/data-sources` | Data source config CRUD |
| `/api/v1/dashboard` | Aggregated portfolio + signal + risk overview |
| `/ws/{user_id}` | WebSocket real-time updates |

Interactive docs: `http://localhost:8000/docs`

## Pattern Detectors

Five detectors are available for scanning and backtesting:

| Pattern | Parameters |
|---|---|
| `pin_bar` | `min_wick_ratio`, `max_body_pct` |
| `breakout` | `lookback`, `min_range_bars` |
| `flag` | `pole_bars`, `flag_bars`, `min_pole_gain_pct`, `max_flag_retracement_pct` |
| `vwap_bounce` | `proximity_pct`, `lookback` |
| `volume_spike` | `min_spike_ratio`, `lookback` |

## Automation Modes

- **`semi_auto`**: Scanner creates a `pending` signal; user confirms via `/signals/{id}/confirm` to execute
- **`full_auto`**: Scanner creates an `executed` signal immediately

Signal statuses: `pending` → `executed` (confirmed) or `rejected` or `expired`

## Development

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run tests
python3.12 -m pytest --cov=app tests/

# Run API locally (requires Postgres + Redis)
uvicorn app.main:app --reload

# Run migrations
alembic upgrade head
```

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | Async Postgres URL (`postgresql+asyncpg://...`) |
| `SYNC_DATABASE_URL` | Sync Postgres URL for Alembic (`postgresql://...`) |
| `REDIS_URL` | Redis URL (`redis://localhost:6379/0`) |
| `SECRET_KEY` | JWT signing secret (min 32 chars, keep secret) |
| `ENCRYPTION_KEY` | 32-char key for encrypting brokerage tokens |
| `ENVIRONMENT` | `development` or `production` |

## Roadmap (v1.1)

- AI Trade Review: LLM analysis of journal entries with playbook suggestions
- Multi-Timeframe Alignment Score: confidence scoring across timeframes
- Options Flow Integration: unusual options activity as context signals
