"""Questrade API client implementing the BaseBroker interface."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo
import httpx

EASTERN = ZoneInfo("America/Toronto")


def _to_eastern_iso(dt: datetime) -> str:
    """Convert a naive (UTC-assumed) or aware datetime to Eastern time ISO string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(EASTERN).isoformat()
from app.brokerage.base import (
    BaseBroker, AccountInfo, Position, Balance, Quote,
    OptionChain, PlacedOrder, Candle, OrderSide, OrderType
)
from app.brokerage.questrade.models import (
    QuestradeAccount, QuestradePosition, QuestradeCurrency,
    QuestradeQuote, QuestradeCandle
)


# Map our unified OrderType to Questrade's format
ORDER_TYPE_MAP = {
    OrderType.market: "Market",
    OrderType.limit: "Limit",
    OrderType.stop: "Stop",
    OrderType.stop_limit: "StopLimit",
}

ORDER_SIDE_MAP = {
    OrderSide.buy: "Buy",
    OrderSide.sell: "Sell",
    OrderSide.buy_to_open: "BuyToOpen",
    OrderSide.sell_to_open: "SellToOpen",
    OrderSide.buy_to_close: "BuyToClose",
    OrderSide.sell_to_close: "SellToClose",
}

# Interval string mapping for candles
INTERVAL_MAP = {
    "1m": "OneMinute",
    "2m": "TwoMinutes",
    "3m": "ThreeMinutes",
    "4m": "FourMinutes",
    "5m": "FiveMinutes",
    "10m": "TenMinutes",
    "15m": "FifteenMinutes",
    "20m": "TwentyMinutes",
    "30m": "HalfHour",
    "1h": "OneHour",
    "2h": "TwoHours",
    "4h": "FourHours",
    "1d": "OneDay",
    "1w": "OneWeek",
    "1mo": "OneMonth",
}


class QuestradeClient(BaseBroker):
    """
    Questrade REST API client.
    Docs: https://www.questrade.com/api/documentation
    """

    def __init__(self, access_token: str, api_server: str):
        self.access_token = access_token
        self.api_server = api_server.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        self._refresh_callback = None  # Set by dependency injection

    def _get_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=f"{self.api_server}/v1/",
                headers=self._get_headers(),
                timeout=15.0,
            )
        return self._client

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        client = await self._get_client()
        response = await client.request(method, path, **kwargs)
        if response.status_code == 401 and self._refresh_callback:
            # Token expired, try refresh
            new_token = await self._refresh_callback()
            if new_token:
                self.access_token = new_token
                self._client = None
                client = await self._get_client()
                response = await client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    async def refresh_token(self) -> bool:
        """Handled externally via the auth module."""
        return False

    async def get_accounts(self) -> list[AccountInfo]:
        data = await self._request("GET", "accounts")
        accounts = []
        for acc in data.get("accounts", []):
            accounts.append(AccountInfo(
                account_id=acc["number"],
                account_type=acc["type"],
                currency="CAD",
                is_primary=acc.get("isPrimary", False),
                status=acc.get("status", "Active"),
            ))
        return accounts

    async def get_positions(self, account_id: str) -> list[Position]:
        data = await self._request("GET", f"accounts/{account_id}/positions")
        positions = []
        for pos in data.get("positions", []):
            qty = Decimal(str(pos.get("openQuantity", 0)))
            if qty == 0:
                continue
            avg_cost = Decimal(str(pos.get("averageEntryPrice", 0)))
            current = Decimal(str(pos.get("currentPrice", 0)))
            market_val = Decimal(str(pos.get("currentMarketValue", 0)))
            pnl = Decimal(str(pos.get("openPnl", 0)))
            pnl_pct = (pnl / (avg_cost * qty) * 100) if (avg_cost * qty) != 0 else Decimal("0")
            positions.append(Position(
                symbol=pos["symbol"],
                quantity=qty,
                average_cost=avg_cost,
                current_price=current,
                market_value=market_val,
                pnl=pnl,
                pnl_pct=pnl_pct,
                instrument_type="stock",
            ))
        return positions

    async def get_balances(self, account_id: str) -> list[Balance]:
        data = await self._request("GET", f"accounts/{account_id}/balances")
        balances = []
        for bal in data.get("combinedBalances", []):
            balances.append(Balance(
                currency=bal.get("currency", "CAD"),
                cash=Decimal(str(bal.get("cash", 0))),
                market_value=Decimal(str(bal.get("marketValue", 0))),
                total_equity=Decimal(str(bal.get("totalEquity", 0))),
                buying_power=Decimal(str(bal.get("buyingPower", 0))),
                maintenance_excess=Decimal(str(bal.get("maintenanceExcess", 0))),
            ))
        return balances

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        # Resolve symbols to IDs in parallel
        import asyncio

        async def resolve_symbol(sym: str) -> int | None:
            data = await self._request("GET", "symbols/search", params={"prefix": sym})
            for result in data.get("symbols", []):
                if result["symbol"].upper() == sym.upper():
                    return result["symbolId"]
            return None

        results = await asyncio.gather(*[resolve_symbol(s) for s in symbols])
        symbol_ids = [sid for sid in results if sid is not None]

        if not symbol_ids:
            return []

        ids_str = ",".join(str(i) for i in symbol_ids)
        data = await self._request("GET", "markets/quotes", params={"ids": ids_str})
        quotes = []
        for q in data.get("quotes", []):
            quotes.append(Quote(
                symbol=q["symbol"],
                symbol_id=q["symbolId"],
                bid=Decimal(str(q.get("bidPrice") or 0)),
                ask=Decimal(str(q.get("askPrice") or 0)),
                last=Decimal(str(q.get("lastTradePrice") or 0)),
                open=Decimal(str(q.get("openPrice") or 0)),
                high=Decimal(str(q.get("highPrice") or 0)),
                low=Decimal(str(q.get("lowPrice") or 0)),
                volume=q.get("volume") or 0,
                timestamp=datetime.utcnow(),
            ))
        return quotes

    async def search_symbols(self, query: str, offset: int = 0) -> list[dict]:
        data = await self._request(
            "GET", "symbols/search",
            params={"prefix": query, "offset": offset}
        )
        return data.get("symbols", [])

    async def get_option_chain(
        self, symbol: str, expiry_date: Optional[str] = None
    ) -> list[OptionChain]:
        # Get symbol ID first
        search = await self._request("GET", "symbols/search", params={"prefix": symbol})
        symbol_id = None
        for s in search.get("symbols", []):
            if s["symbol"].upper() == symbol.upper():
                symbol_id = s["symbolId"]
                break
        if not symbol_id:
            return []

        data = await self._request("GET", f"symbols/{symbol_id}/options")
        chains = []
        for chain in data.get("optionChain", []):
            expiry = chain.get("expiryDate", "")
            if expiry_date and expiry != expiry_date:
                continue
            calls, puts = [], []
            for root in chain.get("chainPerRoot", []):
                for opt in root.get("chainPerStrikePrice", []):
                    strike = opt.get("strikePrice", 0)
                    if opt.get("callSymbolId"):
                        calls.append({"strikePrice": strike, "symbolId": opt["callSymbolId"]})
                    if opt.get("putSymbolId"):
                        puts.append({"strikePrice": strike, "symbolId": opt["putSymbolId"]})
            chains.append(OptionChain(
                underlying_symbol=symbol,
                expiry_date=expiry,
                calls=calls,
                puts=puts,
            ))
        return chains

    async def get_candles(
        self,
        symbol_id: int,
        start_time: datetime,
        end_time: datetime,
        interval: str = "OneDay",
    ) -> list[Candle]:
        qt_interval = INTERVAL_MAP.get(interval, interval)
        data = await self._request(
            "GET",
            f"markets/candles/{symbol_id}",
            params={
                "startTime": _to_eastern_iso(start_time),
                "endTime": _to_eastern_iso(end_time),
                "interval": qt_interval,
            },
        )
        candles = []
        for c in data.get("candles", []):
            candles.append(Candle(
                time=datetime.fromisoformat(c["start"].replace("Z", "+00:00")),
                open=Decimal(str(c["open"])),
                high=Decimal(str(c["high"])),
                low=Decimal(str(c["low"])),
                close=Decimal(str(c["close"])),
                volume=c.get("volume", 0),
            ))
        return candles

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
        payload = {
            "symbolId": symbol_id,
            "quantity": quantity,
            "orderType": ORDER_TYPE_MAP[order_type],
            "timeInForce": "Day",
            "action": ORDER_SIDE_MAP[side],
            "primaryRoute": "AUTO",
            "secondaryRoute": "AUTO",
        }
        if limit_price is not None:
            payload["limitPrice"] = float(limit_price)
        if stop_price is not None:
            payload["stopPrice"] = float(stop_price)

        data = await self._request(
            "POST", f"accounts/{account_id}/orders", json=payload
        )
        orders = data.get("orders", [data])
        order = orders[0] if orders else data
        return PlacedOrder(
            broker_order_id=str(order.get("id", "")),
            symbol=str(symbol_id),
            side=side.value,
            quantity=quantity,
            order_type=order_type.value,
            status=order.get("state", "submitted"),
            limit_price=limit_price,
        )

    async def cancel_order(self, account_id: str, order_id: str) -> bool:
        try:
            await self._request("DELETE", f"accounts/{account_id}/orders/{order_id}")
            return True
        except httpx.HTTPError:
            return False

    async def get_orders(
        self, account_id: str, start_time: Optional[datetime] = None
    ) -> list[dict]:
        params = {"stateFilter": "All"}
        if start_time:
            params["startTime"] = start_time.isoformat() + "-05:00"
        data = await self._request("GET", f"accounts/{account_id}/orders", params=params)
        return data.get("orders", [])

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
