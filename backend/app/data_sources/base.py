"""BaseDataSource ABC — all market data adapters implement this interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class NormalizedCandle:
    """Canonical candle format returned by all data sources."""
    time: datetime          # UTC
    symbol: str
    timeframe: str          # e.g. "1min", "5min", "1day"
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0      # 0 when unavailable (extended hours, options with no trades)
    vwap: Decimal | None = None


@dataclass
class SymbolResult:
    symbol: str
    name: str
    exchange: str
    instrument_type: str    # "stock" | "etf" | "option"


class BaseDataSource(ABC):
    """
    Abstract interface for market data providers.

    Adding a new provider means implementing this interface — no changes to
    strategies, backtesting, or automation code.

    Subclasses MUST define a class attribute `source_type` matching a `DataSourceType` enum value.
    """

    source_type: str  # Must match DataSourceType enum value

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not isinstance(cls.__dict__.get("source_type"), str):
            raise TypeError(
                f"{cls.__name__} must define class attribute 'source_type: str'"
            )

    @abstractmethod
    async def fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[NormalizedCandle]:
        """
        Fetch OHLCV candles for `symbol` in the given time range.

        Returns candles sorted by time ascending.
        Raises `DataSourceError` on API failures.
        """

    @abstractmethod
    async def search_symbols(self, query: str) -> list[SymbolResult]:
        """
        Search for symbols matching `query`.

        Returns up to 20 results ranked by relevance.
        """


class DataSourceError(Exception):
    """Raised when a data source fails to fetch data."""
