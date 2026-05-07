"""
WebSocket connection manager with Redis pub/sub for horizontal scaling.

Architecture:
- Each server instance maintains its own set of WebSocket connections
- Redis pub/sub broadcasts messages across all server instances
- When a message needs to be sent to a room:
  1. Publish to Redis channel 'game:{room_code}'
  2. All server instances receive the message
  3. Each instance sends to locally connected clients
"""

import asyncio
import json
from typing import Any

from fastapi import WebSocket

from app.core.logging import get_logger
from app.redis import get_redis_client

logger = get_logger(__name__)

# Type aliases for WebSocket connection tracking
RoomConnections = dict[str, set[WebSocket]]
PlayerConnections = dict[str, WebSocket]
RoomSubscriptions = dict[str, asyncio.Task[None]]


class ConnectionManager:
    """
    Manages WebSocket connections for game rooms.

    Uses Redis pub/sub for cross-server communication.
    """

    def __init__(self) -> None:
        # room_code -> set of WebSocket connections on THIS server instance
        self._rooms: dict[str, set[WebSocket]] = {}
        # player_id -> WebSocket (for direct messaging)
        self._players: dict[str, WebSocket] = {}
        # Active Redis subscriptions
        self._subscriptions: dict[str, asyncio.Task[None]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        room_code: str,
        player_id: str,
    ) -> None:
        """
        Accept a WebSocket connection and add to room.

        Starts Redis subscription for the room if not already active.
        """
        await websocket.accept()

        async with self._lock:
            # Add to room
            if room_code not in self._rooms:
                self._rooms[room_code] = set()
                # Start Redis subscription for this room
                await self._subscribe_to_room(room_code)

            self._rooms[room_code].add(websocket)
            self._players[player_id] = websocket

        logger.info(
            "websocket_connected",
            room_code=room_code,
            player_id=player_id,
            local_connections=len(self._rooms.get(room_code, set())),
        )

    async def disconnect(
        self,
        websocket: WebSocket,
        room_code: str,
        player_id: str,
    ) -> None:
        """Remove a WebSocket connection from room."""
        async with self._lock:
            # Remove from room
            if room_code in self._rooms:
                self._rooms[room_code].discard(websocket)

                # Clean up empty room
                if not self._rooms[room_code]:
                    del self._rooms[room_code]
                    await self._unsubscribe_from_room(room_code)

            # Remove from player mapping
            self._players.pop(player_id, None)

        logger.info(
            "websocket_disconnected",
            room_code=room_code,
            player_id=player_id,
        )

    async def broadcast_to_room(
        self,
        room_code: str,
        message: dict[str, Any],
        exclude_player_id: str | None = None,
    ) -> None:
        """
        Broadcast message to all players in a room across ALL server instances.

        Uses Redis pub/sub to reach players connected to other servers.
        """
        payload = {
            "message": message,
            "exclude_player_id": exclude_player_id,
        }

        try:
            redis_client = get_redis_client()
            channel = f"game:{room_code}"
            await redis_client.publish(channel, json.dumps(payload))
            logger.debug(
                "redis_publish",
                channel=channel,
                message_type=message.get("type"),
            )
        except Exception as e:
            logger.error("redis_publish_error", error=str(e), room_code=room_code)
            # Fallback: send to local connections only
            await self._send_to_local_room(room_code, message, exclude_player_id)

    async def send_to_player(
        self,
        player_id: str,
        message: dict[str, Any],
    ) -> None:
        """Send message to a specific player (local connection only)."""
        websocket = self._players.get(player_id)
        if websocket:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(
                    "websocket_send_error",
                    player_id=player_id,
                    error=str(e),
                )

    async def _send_to_local_room(
        self,
        room_code: str,
        message: dict[str, Any],
        exclude_player_id: str | None = None,
    ) -> None:
        """Send message to all local WebSocket connections in a room."""
        connections = self._rooms.get(room_code, set()).copy()

        for websocket in connections:
            # Find player_id for this websocket
            player_id = next(
                (pid for pid, ws in self._players.items() if ws == websocket),
                None,
            )

            if exclude_player_id and player_id == exclude_player_id:
                continue

            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(
                    "websocket_send_failed",
                    room_code=room_code,
                    error=str(e),
                )

    async def _subscribe_to_room(self, room_code: str) -> None:
        """Start Redis subscription for a room channel."""
        if room_code in self._subscriptions:
            return

        async def subscriber() -> None:
            try:
                redis_client = get_redis_client()
                pubsub = redis_client.pubsub()
                channel = f"game:{room_code}"
                await pubsub.subscribe(channel)

                logger.info("redis_subscribed", channel=channel)

                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            payload = json.loads(message["data"])
                            await self._send_to_local_room(
                                room_code,
                                payload["message"],
                                payload.get("exclude_player_id"),
                            )
                        except json.JSONDecodeError:
                            logger.warning("redis_message_decode_error")

            except asyncio.CancelledError:
                logger.info("redis_subscription_cancelled", room_code=room_code)
            except Exception as e:
                logger.error("redis_subscription_error", error=str(e))

        task = asyncio.create_task(subscriber())
        self._subscriptions[room_code] = task

    async def _unsubscribe_from_room(self, room_code: str) -> None:
        """Cancel Redis subscription for a room channel."""
        task = self._subscriptions.pop(room_code, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("redis_unsubscribed", room_code=room_code)

    def get_local_player_count(self, room_code: str) -> int:
        """Get number of players connected to THIS server instance."""
        return len(self._rooms.get(room_code, set()))

    async def close_all(self) -> None:
        """Close all connections and subscriptions. Call on shutdown."""
        # Cancel all subscriptions
        for room_code in list(self._subscriptions.keys()):
            await self._unsubscribe_from_room(room_code)

        # Close all WebSockets
        for room_code, connections in self._rooms.items():
            for websocket in connections:
                try:
                    await websocket.close()
                except Exception:
                    pass

        self._rooms.clear()
        self._players.clear()


# Singleton instance
connection_manager = ConnectionManager()
