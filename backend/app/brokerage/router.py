"""Brokerage API router — connect, accounts, positions, quotes, orders."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.dependencies import CurrentUser
from app.brokerage.questrade.auth import (
    exchange_code_for_tokens,
    get_active_connection,
    refresh_questrade_token,
    decrypt_token,
)
from app.brokerage.questrade.client import QuestradeClient
from app.models.user import BrokerageConnection

router = APIRouter(prefix="/brokerage", tags=["brokerage"])


# ─── Dependency: get authenticated Questrade client ───────────────────────────

async def get_questrade_client(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> QuestradeClient:
    connection = await get_active_connection(db, current_user.id)
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Questrade connection found. Please connect your account.",
        )

    # Refresh if token expired or within 5 minutes of expiry
    from datetime import timedelta
    if connection.expires_at and connection.expires_at <= datetime.utcnow() + timedelta(minutes=5):
        connection = await refresh_questrade_token(db, connection)
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Questrade token expired. Please reconnect your account.",
            )

    access_token = decrypt_token(connection.access_token_encrypted)
    return QuestradeClient(
        access_token=access_token,
        api_server=connection.api_server,
    )


# ─── Connection endpoints ──────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    refresh_token: str


class ConnectionStatusResponse(BaseModel):
    is_connected: bool
    broker_type: Optional[str] = None
    api_server: Optional[str] = None
    expires_at: Optional[datetime] = None
    connection_id: Optional[uuid.UUID] = None


@router.post("/connect/questrade", status_code=status.HTTP_201_CREATED)
async def connect_questrade(
    request: ConnectRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Connect a Questrade account using a refresh token from the API hub."""
    try:
        connection = await exchange_code_for_tokens(
            db=db,
            user_id=current_user.id,
            refresh_token=request.refresh_token,
        )
        return {
            "message": "Questrade account connected successfully",
            "api_server": connection.api_server,
            "expires_at": connection.expires_at,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to connect Questrade: {str(e)}",
        )


@router.get("/status", response_model=ConnectionStatusResponse)
async def get_connection_status(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    connection = await get_active_connection(db, current_user.id)
    if not connection:
        return ConnectionStatusResponse(is_connected=False)
    return ConnectionStatusResponse(
        is_connected=True,
        broker_type=connection.broker_type,
        api_server=connection.api_server,
        expires_at=connection.expires_at,
        connection_id=connection.id,
    )


@router.delete("/disconnect")
async def disconnect_brokerage(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    connection = await get_active_connection(db, current_user.id)
    if connection:
        connection.is_active = False
    return {"message": "Disconnected successfully"}


# ─── Account endpoints ─────────────────────────────────────────────────────────

@router.get("/accounts")
async def get_accounts(
    client: Annotated[QuestradeClient, Depends(get_questrade_client)],
):
    accounts = await client.get_accounts()
    return {"accounts": [vars(a) for a in accounts]}


@router.get("/accounts/{account_id}/positions")
async def get_positions(
    account_id: str,
    client: Annotated[QuestradeClient, Depends(get_questrade_client)],
):
    positions = await client.get_positions(account_id)
    return {"positions": [vars(p) for p in positions]}


@router.get("/accounts/{account_id}/balances")
async def get_balances(
    account_id: str,
    client: Annotated[QuestradeClient, Depends(get_questrade_client)],
):
    balances = await client.get_balances(account_id)
    return {"balances": [vars(b) for b in balances]}


@router.get("/accounts/{account_id}/orders")
async def get_account_orders(
    account_id: str,
    client: Annotated[QuestradeClient, Depends(get_questrade_client)],  # type: ignore[assignment]
    start_time: Optional[datetime] = None,
):
    orders = await client.get_orders(account_id, start_time)
    return {"orders": orders}


# ─── Market data endpoints ─────────────────────────────────────────────────────

@router.get("/quotes")
async def get_quotes(
    symbols: str,  # Comma-separated: "AAPL,SPY,TSLA"
    client: Annotated[QuestradeClient, Depends(get_questrade_client)],
):
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    quotes = await client.get_quotes(symbol_list)
    return {"quotes": [vars(q) for q in quotes]}


@router.get("/symbols/search")
async def search_symbols(
    client: Annotated[QuestradeClient, Depends(get_questrade_client)],
    query: str = "",
    offset: int = 0,
):
    results = await client.search_symbols(query, offset)
    return {"symbols": results}


@router.get("/symbols/{symbol}/options")
async def get_option_chain(
    symbol: str,
    client: Annotated[QuestradeClient, Depends(get_questrade_client)],
    expiry_date: Optional[str] = None,
):
    chains = await client.get_option_chain(symbol.upper(), expiry_date)
    result = []
    for chain in chains:
        result.append({
            "underlying_symbol": chain.underlying_symbol,
            "expiry_date": chain.expiry_date,
            "calls": chain.calls,
            "puts": chain.puts,
        })
    return {"option_chains": result}


@router.get("/candles/{symbol_id}")
async def get_candles(
    symbol_id: int,
    start_time: datetime,
    end_time: datetime,
    client: Annotated[QuestradeClient, Depends(get_questrade_client)],
    interval: str = "1d",
):
    candles = await client.get_candles(symbol_id, start_time, end_time, interval)
    return {
        "candles": [
            {
                "time": c.time.isoformat(),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": c.volume,
            }
            for c in candles
        ]
    }


# ─── Order placement ───────────────────────────────────────────────────────────

class PlaceOrderRequest(BaseModel):
    account_id: str
    symbol_id: int
    side: str
    quantity: int
    order_type: str
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    # Risk fields: stop_loss_price is your max-loss exit, used to compute trade_risk
    stop_loss_price: Optional[Decimal] = None


@router.post("/orders")
async def place_order(
    request: PlaceOrderRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    client: Annotated[QuestradeClient, Depends(get_questrade_client)],
):
    """Place an order via Questrade with pre-trade risk validation."""
    from app.brokerage.base import OrderSide, OrderType
    from app.risk.service import validate_pre_trade, RiskViolation

    try:
        side = OrderSide(request.side)
        order_type = OrderType(request.order_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Compute dollar risk for this trade
    trade_risk = Decimal("0")
    if request.stop_loss_price and request.limit_price:
        trade_risk = abs(request.limit_price - request.stop_loss_price) * request.quantity

    # Fetch account equity for percentage-based limits
    account_equity: Optional[Decimal] = None
    try:
        balances = await client.get_balances(request.account_id)
        account_equity = sum((b.total_equity for b in balances), Decimal("0")) or None
    except Exception:
        pass  # Proceed with absolute limits if equity fetch fails

    try:
        await validate_pre_trade(db, current_user.id, trade_risk, account_equity)
    except RiskViolation as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    placed = await client.place_order(
        account_id=request.account_id,
        symbol_id=request.symbol_id,
        side=side,
        quantity=request.quantity,
        order_type=order_type,
        limit_price=request.limit_price,
        stop_price=request.stop_price,
    )
    return {"order": vars(placed)}


@router.delete("/orders/{account_id}/{order_id}")
async def cancel_order(
    account_id: str,
    order_id: str,
    client: Annotated[QuestradeClient, Depends(get_questrade_client)],
):
    success = await client.cancel_order(account_id, order_id)
    return {"cancelled": success}
