from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.websocket.manager import ws_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await ws_manager.startup(settings.redis_url)
    yield
    # Shutdown
    await ws_manager.shutdown()


app = FastAPI(
    title="Trading Automation API",
    description="Trading automation platform with Questrade integration",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
from app.auth.router import router as auth_router
from app.brokerage.router import router as brokerage_router
from app.risk.router import router as risk_router
from app.strategies.router import router as strategies_router
from app.journal.router import router as journal_router
from app.backtesting.router import router as backtesting_router
from app.automation.router import router as automation_router
from app.data_sources.router import router as data_sources_router

app.include_router(auth_router, prefix="/api/v1")
app.include_router(brokerage_router, prefix="/api/v1")
app.include_router(risk_router, prefix="/api/v1")
app.include_router(strategies_router, prefix="/api/v1")
app.include_router(journal_router, prefix="/api/v1")
app.include_router(backtesting_router, prefix="/api/v1")
app.include_router(automation_router, prefix="/api/v1")
app.include_router(data_sources_router, prefix="/api/v1")


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


# ─── WebSocket endpoint ────────────────────────────────────────────────────────

from jose import JWTError
from app.auth.service import decode_token


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, token: str = ""):
    """
    WebSocket endpoint for real-time updates.
    Connect with: ws://host/ws/{user_id}?token=<jwt>
    """
    # Validate token
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    try:
        payload = decode_token(token)
        token_user_id = payload.get("sub")
        if token_user_id != user_id:
            await websocket.close(code=4003, reason="Forbidden")
            return
    except JWTError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await ws_manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive; handle client messages
            data = await websocket.receive_text()
            # Client can send heartbeat or subscribe messages
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, user_id)
