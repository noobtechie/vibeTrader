"""Abstract base class for all brokerage integrations."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, AsyncIterator
import enum


class OrderSide(str, enum.Enum):
    buy = "buy"
    sell = "sell"
    buy_to_open = "buy_to_open"
    sell_to_open = "sell_to_open"
    buy_to_close = "buy_to_close"
    sell_to_close = "sell_to_close"


class OrderType(str, enum.Enum):
    market = "market"
    limit = "limit"
    stop = "stop"
    stop_limit = "stop_limit"


@dataclass
class AccountInfo:
    account_id: str
    account_type: str
    currency: str
    is_primary: bool
    status: str


@dataclass
class Position:
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    current_price: Decimal
    market_value: Decimal
    pnl: Decimal
    pnl_pct: Decimal
    instrument_type: str


@dataclass
class Balance:
    currency: str
    cash: Decimal
    market_value: Decimal
    total_equity: Decimal
    buying_power: Decimal
    maintenance_excess: Decimal


@dataclass
class Quote:
    symbol: str
    symbol_id: int
    bid: Decimal
    ask: Decimal
    last: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    volume: int
    timestamp: datetime


@dataclass
class OptionChain:
    underlying_symbol: str
    expiry_date: str
    calls: list[dict]
    puts: list[dict]


@dataclass
class PlacedOrder:
    broker_order_id: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    status: str
    limit_price: Optional[Decimal] = None


@dataclass
class Candle:
    time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class BaseBroker(ABC):
    """
    Abstract interface for brokerage integrations.
    All brokers must implement these methods.
    Adding a new broker = implementing this interface.
    """

    @abstractmethod
    async def refresh_token(self) -> bool:
        """Refresh the access token. Returns True if successful."""
        ...

    @abstractmethod
    async def get_accounts(self) -> list[AccountInfo]:
        """Get all accounts for the authenticated user."""
        ...

    @abstractmethod
    async def get_positions(self, account_id: str) -> list[Position]:
        """Get all open positions for an account."""
        ...

    @abstractmethod
    async def get_balances(self, account_id: str) -> list[Balance]:
        """Get account balances."""
        ...

    @abstractmethod
    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        """Get real-time quotes for a list of symbols."""
        ...

    @abstractmethod
    async def search_symbols(self, query: str, offset: int = 0) -> list[dict]:
        """Search for symbols by name or ticker."""
        ...

    @abstractmethod
    async def get_option_chain(
        self,
        symbol: str,
        expiry_date: Optional[str] = None,
    ) -> list[OptionChain]:
        """Get option chain for a symbol."""
        ...

    @abstractmethod
    async def get_candles(
        self,
        symbol_id: int,
        start_time: datetime,
        end_time: datetime,
        interval: str = "OneDay",
    ) -> list[Candle]:
        """Get historical OHLCV candles."""
        ...

    @abstractmethod
    async def place_order(
        self,
        account_id: str,
        symbol_id: int,
        side: OrderSide,
        quantity: int,
        order_type: OrderType,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
    ) -> PlacedOrder:
        """Place an order. Returns the placed order details."""
        ...

    @abstractmethod
    async def cancel_order(self, account_id: str, order_id: str) -> bool:
        """Cancel an order. Returns True if successful."""
        ...

    @abstractmethod
    async def get_orders(
        self, account_id: str, start_time: Optional[datetime] = None
    ) -> list[dict]:
        """Get orders for an account."""
        ...
