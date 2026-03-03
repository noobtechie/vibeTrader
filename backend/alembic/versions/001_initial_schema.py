"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable TimescaleDB if available
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

    # Users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # Brokerage connections
    op.create_table(
        "brokerage_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("broker_type", sa.Enum("questrade", "interactive_brokers", "alpaca", name="brokertype"), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("api_server", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_brokerage_connections_user_id", "brokerage_connections", ["user_id"])

    # Risk settings
    op.create_table(
        "risk_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("max_risk_per_trade", sa.Numeric(12, 2), nullable=False),
        sa.Column("max_risk_per_trade_pct", sa.Numeric(5, 4), nullable=False),
        sa.Column("max_risk_daily", sa.Numeric(12, 2), nullable=False),
        sa.Column("max_risk_daily_pct", sa.Numeric(5, 4), nullable=False),
        sa.Column("max_risk_weekly", sa.Numeric(12, 2), nullable=False),
        sa.Column("max_risk_weekly_pct", sa.Numeric(5, 4), nullable=False),
        sa.Column("max_risk_monthly", sa.Numeric(12, 2), nullable=False),
        sa.Column("max_risk_monthly_pct", sa.Numeric(5, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, default="CAD"),
        sa.Column("use_percentage", sa.Boolean(), default=True),
        sa.Column("circuit_breaker_active", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # Playbooks
    op.create_table(
        "playbooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("goals", postgresql.JSON(), nullable=True),
        sa.Column("theory", sa.Text(), nullable=True),
        sa.Column("security_criteria", postgresql.JSON(), nullable=True),
        sa.Column("context_rules", postgresql.JSON(), nullable=True),
        sa.Column("trigger_rules", postgresql.JSON(), nullable=True),
        sa.Column("management_rules", postgresql.JSON(), nullable=True),
        sa.Column("sizing_tiers", postgresql.JSON(), nullable=True),
        sa.Column("tracking_abbreviations", postgresql.JSON(), nullable=True),
        sa.Column("questions", postgresql.JSON(), nullable=True),
        sa.Column("ideas", postgresql.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_playbooks_user_id", "playbooks", ["user_id"])

    # Strategies
    op.create_table(
        "strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("playbook_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("automation_mode", sa.Enum("disabled", "semi_auto", "full_auto", name="automationmode"), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=False),
        sa.Column("config", postgresql.JSON(), nullable=True),
        sa.Column("watchlist", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_strategies_playbook_id", "strategies", ["playbook_id"])

    # Trades
    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("instrument_type", sa.Enum("stock", "option", "etf", name="instrumenttype"), nullable=False),
        sa.Column("side", sa.Enum("long", "short", name="tradeside"), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("entry_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("exit_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("stop_loss", sa.Numeric(12, 4), nullable=True),
        sa.Column("take_profit", sa.Numeric(12, 4), nullable=True),
        sa.Column("entry_time", sa.DateTime(), nullable=True),
        sa.Column("exit_time", sa.DateTime(), nullable=True),
        sa.Column("status", sa.Enum("open", "closed", "cancelled", name="tradestatus"), nullable=False),
        sa.Column("pnl", sa.Numeric(12, 2), nullable=True),
        sa.Column("pnl_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("r_multiple", sa.Numeric(8, 4), nullable=True),
        sa.Column("commission", sa.Numeric(8, 2), nullable=False, default=0),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_trades_user_id", "trades", ["user_id"])
    op.create_index("ix_trades_symbol", "trades", ["symbol"])
    op.create_index("ix_trades_entry_time", "trades", ["entry_time"])

    # Orders
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trades.id", ondelete="SET NULL"), nullable=True),
        sa.Column("broker_order_id", sa.String(100), nullable=True),
        sa.Column("account_id", sa.String(100), nullable=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.Enum("buy", "sell", "buy_to_open", "sell_to_open", "buy_to_close", "sell_to_close", name="orderside"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("order_type", sa.Enum("market", "limit", "stop", "stop_limit", name="ordertype"), nullable=False),
        sa.Column("limit_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("stop_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("filled_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("filled_quantity", sa.Integer(), nullable=False, default=0),
        sa.Column("status", sa.Enum("pending", "submitted", "filled", "partially_filled", "cancelled", "rejected", name="orderstatus"), nullable=False),
        sa.Column("placed_at", sa.DateTime(), nullable=False),
        sa.Column("filled_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_broker_order_id", "orders", ["broker_order_id"])

    # Journal entries
    op.create_table(
        "journal_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trades.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSON(), nullable=True),
        sa.Column("screenshots", postgresql.JSON(), nullable=True),
        sa.Column("context_abbreviation", sa.String(50), nullable=True),
        sa.Column("trigger_abbreviation", sa.String(50), nullable=True),
        sa.Column("management_abbreviation", sa.String(50), nullable=True),
        sa.Column("sizing_tier", sa.String(50), nullable=True),
        sa.Column("confidence_before", sa.Integer(), nullable=True),
        sa.Column("execution_quality", sa.Integer(), nullable=True),
        sa.Column("followed_playbook", sa.Boolean(), nullable=True),
        sa.Column("lessons_learned", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_journal_entries_user_id", "journal_entries", ["user_id"])
    op.create_index("ix_journal_entries_entry_date", "journal_entries", ["entry_date"])

    # Risk events (TimescaleDB hypertable)
    op.create_table(
        "risk_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.Enum("limit_hit", "circuit_break", "warning", name="riskeventtype"), nullable=False),
        sa.Column("limit_type", sa.Enum("per_trade", "daily", "weekly", "monthly", name="limittype"), nullable=False),
        sa.Column("current_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("limit_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("message", sa.String(500), nullable=True),
    )
    op.create_index("ix_risk_events_user_id", "risk_events", ["user_id"])
    op.create_index("ix_risk_events_triggered_at", "risk_events", ["triggered_at"])

    # Candles (TimescaleDB hypertable)
    op.create_table(
        "candles",
        sa.Column("time", sa.DateTime(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("open", sa.Numeric(12, 4), nullable=False),
        sa.Column("high", sa.Numeric(12, 4), nullable=False),
        sa.Column("low", sa.Numeric(12, 4), nullable=False),
        sa.Column("close", sa.Numeric(12, 4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("vwap", sa.Numeric(12, 4), nullable=True),
        sa.PrimaryKeyConstraint("time", "symbol", "timeframe", "source"),
    )

    # Data source configs
    op.create_table(
        "data_source_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.Enum("questrade", "polygon", "alpha_vantage", "yahoo_finance", name="datasourcetype"), nullable=False),
        sa.Column("credentials_encrypted", sa.String(2000), nullable=True),
        sa.Column("is_default", sa.Boolean(), default=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("config", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_data_source_configs_user_id", "data_source_configs", ["user_id"])

    # Create hypertables (will silently fail if TimescaleDB not available)
    try:
        op.execute("SELECT create_hypertable('candles', 'time', if_not_exists => TRUE);")
        op.execute("SELECT create_hypertable('risk_events', 'triggered_at', if_not_exists => TRUE);")
    except Exception:
        pass


def downgrade() -> None:
    op.drop_table("data_source_configs")
    op.drop_table("candles")
    op.drop_table("risk_events")
    op.drop_table("journal_entries")
    op.drop_table("orders")
    op.drop_table("trades")
    op.drop_table("strategies")
    op.drop_table("playbooks")
    op.drop_table("risk_settings")
    op.drop_table("brokerage_connections")
    op.drop_table("users")

    # Drop enums
    for enum_name in [
        "brokertype", "automationmode", "instrumenttype", "tradeside",
        "tradestatus", "orderside", "ordertype", "orderstatus",
        "riskeventtype", "limittype", "datasourcetype"
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")
