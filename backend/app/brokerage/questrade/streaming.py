"""Questrade WebSocket market data streaming."""
import asyncio
import json
import logging
from typing import Callable, Optional
import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class QuestradeStreamer:
    """
    Streams real-time quotes from Questrade's streaming endpoint.
    Publishes updates via a callback function.
    """

    def __init__(
        self,
        access_token: str,
        api_server: str,
        on_quote: Callable[[dict], None],
    ):
        self.access_token = access_token
        self.api_server = api_server.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
        self.on_quote = on_quote
        self._ws = None
        self._running = False
        self._subscribed_ids: set[int] = set()

    async def connect(self):
        """Establish WebSocket connection."""
        # Get streaming port from Questrade
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_server.replace('wss://', 'https://').replace('ws://', 'http://')}/v1/markets/quotes",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params={"ids": "9"},  # Dummy request to get streaming info
            )

        ws_url = f"{self.api_server}/v1/markets/quotes?stream=true&mode=RawSocket"
        self._ws = await websockets.connect(
            ws_url,
            extra_headers={"Authorization": f"Bearer {self.access_token}"},
        )
        self._running = True
        logger.info("Questrade streaming connection established")

    async def subscribe(self, symbol_ids: list[int]):
        """Subscribe to quotes for given symbol IDs."""
        self._subscribed_ids.update(symbol_ids)
        if self._ws:
            await self._ws.send(json.dumps({
                "type": "subscribe",
                "symbolIds": list(self._subscribed_ids),
            }))

    async def listen(self):
        """Listen for incoming messages. Run in a background task."""
        if not self._ws:
            return
        try:
            async for message in self._ws:
                if not self._running:
                    break
                try:
                    data = json.loads(message)
                    await self.on_quote(data)
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"Failed to process streaming message: {e}")
        except ConnectionClosed:
            logger.info("Questrade streaming connection closed")
        finally:
            self._running = False

    async def disconnect(self):
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
