"""Canonical enum definitions shared across models and brokerage layer."""
import enum


class BrokerType(str, enum.Enum):
    questrade = "questrade"
    interactive_brokers = "interactive_brokers"
    alpaca = "alpaca"


class AutomationMode(str, enum.Enum):
    disabled = "disabled"
    semi_auto = "semi_auto"
    full_auto = "full_auto"


class InstrumentType(str, enum.Enum):
    stock = "stock"
    option = "option"
    etf = "etf"


class TradeSide(str, enum.Enum):
    long = "long"
    short = "short"


class TradeStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    cancelled = "cancelled"


class OrderType(str, enum.Enum):
    market = "market"
    limit = "limit"
    stop = "stop"
    stop_limit = "stop_limit"


class OrderSide(str, enum.Enum):
    buy = "buy"
    sell = "sell"
    buy_to_open = "buy_to_open"
    sell_to_open = "sell_to_open"
    buy_to_close = "buy_to_close"
    sell_to_close = "sell_to_close"


class OrderStatus(str, enum.Enum):
    pending = "pending"
    submitted = "submitted"
    filled = "filled"
    partially_filled = "partially_filled"
    cancelled = "cancelled"
    rejected = "rejected"


class RiskEventType(str, enum.Enum):
    limit_hit = "limit_hit"
    circuit_break = "circuit_break"
    warning = "warning"


class LimitType(str, enum.Enum):
    per_trade = "per_trade"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    circuit_breaker = "circuit_breaker"


class DataSourceType(str, enum.Enum):
    questrade = "questrade"
    polygon = "polygon"
    alpha_vantage = "alpha_vantage"
    yahoo_finance = "yahoo_finance"
