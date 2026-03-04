"""WebSocket connection manager with Redis pub/sub for cross-process events."""
import asyncio
import json
import logging
from typing import Optional
import uuid
from fastapi import WebSocket
from redis.asyncio import Redis
from app.websocket.events import WSEvent, EventType

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections per user.
    Supports broadcasting from Celery workers via Redis pub/sub.
    """

    def __init__(self):
        # Map user_id -> list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}
        self._redis: Optional[Redis] = None
        self._pubsub_task: Optional[asyncio.Task] = None

    async def startup(self, redis_url: str):
        """Initialize Redis pub/sub listener."""
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._pubsub_task = asyncio.create_task(self._listen_to_redis())
        logger.info("WebSocket manager started with Redis pub/sub")

    async def shutdown(self):
        if self._pubsub_task:
            self._pubsub_task.cancel()
        if self._redis:
            await self._redis.aclose()

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        await self.connect_authenticated(websocket, user_id)

    async def connect_authenticated(self, websocket: WebSocket, user_id: str):
        """Register an already-accepted WebSocket connection."""
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)
        await self.send_to_user(user_id, WSEvent(
            type=EventType.CONNECTED,
            data={"message": "Connected to trading server"},
            user_id=user_id,
        ))
        logger.info(f"WebSocket connected: user={user_id}")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self._connections:
            self._connections[user_id] = [
                ws for ws in self._connections[user_id] if ws != websocket
            ]
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info(f"WebSocket disconnected: user={user_id}")

    async def send_to_user(self, user_id: str, event: WSEvent):
        """Send an event to all connections for a specific user."""
        connections = self._connections.get(user_id, [])
        dead_connections = []
        for ws in connections:
            try:
                await ws.send_text(event.model_dump_json())
            except Exception:
                dead_connections.append(ws)
        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(ws, user_id)

    async def broadcast(self, event: WSEvent):
        """Broadcast an event to all connected users."""
        for user_id in list(self._connections.keys()):
            await self.send_to_user(user_id, event)

    async def publish_to_redis(self, channel: str, event: WSEvent):
        """Publish an event to Redis (called from Celery workers)."""
        if self._redis:
            await self._redis.publish(channel, event.model_dump_json())

    async def _listen_to_redis(self):
        """Listen for messages published by Celery workers."""
        if not self._redis:
            return
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe("trading:*")  # Subscribe to all trading channels
        try:
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    try:
                        data = json.loads(message["data"])
                        event = WSEvent(**data)
                        # Route to specific user or broadcast
                        if event.user_id:
                            await self.send_to_user(event.user_id, event)
                        else:
                            await self.broadcast(event)
                    except Exception as e:
                        logger.error(f"Error processing Redis message: {e}")
        except asyncio.CancelledError:
            await pubsub.close()


# Global singleton
ws_manager = ConnectionManager()
