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
from app.dashboard.router import router as dashboard_router

app.include_router(auth_router, prefix="/api/v1")
app.include_router(brokerage_router, prefix="/api/v1")
app.include_router(risk_router, prefix="/api/v1")
app.include_router(strategies_router, prefix="/api/v1")
app.include_router(journal_router, prefix="/api/v1")
app.include_router(backtesting_router, prefix="/api/v1")
app.include_router(automation_router, prefix="/api/v1")
app.include_router(data_sources_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


# ─── WebSocket endpoint ────────────────────────────────────────────────────────

from jose import JWTError
from app.auth.service import decode_token


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for real-time updates.
    Auth flow: accept connection, await first JSON message {"type":"auth","token":"<jwt>"},
    validate, then start streaming. Token is NOT passed in the URL to prevent log exposure.
    """
    await websocket.accept()

    try:
        # Wait up to 10 seconds for the auth message
        import asyncio
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
    except asyncio.TimeoutError:
        await websocket.close(code=4001, reason="Auth timeout")
        return

    import json
    try:
        msg = json.loads(raw)
        if msg.get("type") != "auth":
            await websocket.close(code=4001, reason="Expected auth message")
            return
        token = msg.get("token", "")
        payload = decode_token(token)
        token_user_id = payload.get("sub")
        if token_user_id != user_id:
            await websocket.close(code=4003, reason="Forbidden")
            return
    except (JWTError, json.JSONDecodeError, Exception):
        await websocket.close(code=4001, reason="Invalid auth")
        return

    # Auth succeeded — hand off to manager (which sends CONNECTED event)
    await ws_manager.connect_authenticated(websocket, user_id)
    try:
        while True:
            # Heartbeat / subscribe messages from client
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, user_id)
