"""WebSocket event type definitions."""
from enum import Enum
from typing import Any
from pydantic import BaseModel
from datetime import datetime


class EventType(str, Enum):
    # Market data
    QUOTE_UPDATE = "quote_update"
    CANDLE_UPDATE = "candle_update"

    # Risk
    RISK_WARNING = "risk_warning"
    RISK_LIMIT_HIT = "risk_limit_hit"
    CIRCUIT_BREAKER = "circuit_breaker"

    # P&L
    PNL_UPDATE = "pnl_update"
    POSITION_UPDATE = "position_update"

    # Orders & Trades
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    TRADE_OPENED = "trade_opened"
    TRADE_CLOSED = "trade_closed"

    # Automation
    SIGNAL_DETECTED = "signal_detected"
    SEMI_AUTO_ALERT = "semi_auto_alert"
    AUTO_ORDER_PLACED = "auto_order_placed"

    # System
    CONNECTED = "connected"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class WSEvent(BaseModel):
    type: EventType
    data: Any
    timestamp: datetime = datetime.utcnow()
    user_id: str | None = None
