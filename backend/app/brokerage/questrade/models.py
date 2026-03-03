"""Questrade API response models."""
from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from datetime import datetime


class QuestradeAccount(BaseModel):
    number: str
    type: str
    status: str
    isPrimary: bool
    isBilling: bool
    clientAccountType: str


class QuestradePosition(BaseModel):
    symbol: str
    symbolId: int
    openQuantity: Decimal
    closedQuantity: Decimal
    currentMarketValue: Decimal
    currentPrice: Decimal
    averageEntryPrice: Decimal
    closedPnl: Decimal
    openPnl: Decimal
    totalCost: Decimal
    isRealTime: bool
    isUnderReorg: bool


class QuestradeCurrency(BaseModel):
    currency: str
    cash: Decimal
    marketValue: Decimal
    totalEquity: Decimal
    buyingPower: Decimal
    maintenanceExcess: Decimal
    isRealTime: bool


class QuestradeQuote(BaseModel):
    symbol: str
    symbolId: int
    tier: Optional[str] = None
    bidPrice: Optional[Decimal] = None
    bidSize: Optional[int] = None
    askPrice: Optional[Decimal] = None
    askSize: Optional[int] = None
    lastTradePriceTrHrs: Optional[Decimal] = None
    lastTradePrice: Optional[Decimal] = None
    lastTradeSize: Optional[int] = None
    lastTradeTick: Optional[str] = None
    lastTradeTime: Optional[str] = None
    volume: Optional[int] = None
    openPrice: Optional[Decimal] = None
    highPrice: Optional[Decimal] = None
    lowPrice: Optional[Decimal] = None
    delay: Optional[int] = None
    isHalted: Optional[bool] = None
    highPrice52: Optional[Decimal] = None
    lowPrice52: Optional[Decimal] = None
    tradeValue: Optional[Decimal] = None
    bidTick: Optional[str] = None
    VWAP: Optional[Decimal] = None


class QuestradeCandle(BaseModel):
    start: datetime
    end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    VWAP: Optional[Decimal] = None


class QuestradeSymbol(BaseModel):
    symbol: str
    symbolId: int
    description: str
    securityType: str
    listingExchange: Optional[str] = None
    isQuotable: bool
    isTradable: bool
    currency: Optional[str] = None


class QuestradeOptionChainEntry(BaseModel):
    expiryDate: str
    description: str
    listingExchange: str
    optionExerciseType: str
    chainPerRoot: list[dict]


class PlaceOrderRequest(BaseModel):
    accountNumber: str
    symbolId: int
    quantity: int
    icebergQuantity: Optional[int] = None
    limitPrice: Optional[Decimal] = None
    stopPrice: Optional[Decimal] = None
    isAllOrNone: bool = False
    isAnonymous: bool = False
    orderType: str  # Market, Limit, Stop, StopLimit
    timeInForce: str = "Day"  # Day, GoodTillCanceled, etc.
    action: str  # Buy, Sell, BuyToCover, SellShort, BuyToOpen, SellToOpen, BuyToClose, SellToClose
    primaryRoute: str = "AUTO"
    secondaryRoute: str = "AUTO"
