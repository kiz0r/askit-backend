import asyncio
import json

from fastapi import WebSocket

from app.core.logging import get_logger
from app.redis import get_redis_client

logger = get_logger(__name__)

# JSON-serializable WebSocket message
WsMessage = dict[str, object]


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}
        self._players: dict[str, WebSocket] = {}
        self._hosts: dict[str, WebSocket] = {}
        self._subscriptions: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def connect_host(self, websocket: WebSocket, room_code: str) -> None:
        await websocket.accept()
        async with self._lock:
            if room_code not in self._rooms:
                self._rooms[room_code] = set()
                await self._subscribe_to_room(room_code)
            self._rooms[room_code].add(websocket)
            self._hosts[room_code] = websocket
        logger.info("host_websocket_connected", room_code=room_code)

    async def disconnect_host(self, websocket: WebSocket, room_code: str) -> None:
        async with self._lock:
            if room_code in self._rooms:
                self._rooms[room_code].discard(websocket)
                if not self._rooms[room_code]:
                    del self._rooms[room_code]
                    await self._unsubscribe_from_room(room_code)
            self._hosts.pop(room_code, None)
        logger.info("host_websocket_disconnected", room_code=room_code)

    async def send_to_host(self, room_code: str, message: WsMessage) -> None:
        websocket = self._hosts.get(room_code)
        if websocket:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error("host_send_error", error=str(e), room_code=room_code)

    async def connect(
        self, websocket: WebSocket, room_code: str, player_id: str
    ) -> None:
        await websocket.accept()
        async with self._lock:
            if room_code not in self._rooms:
                self._rooms[room_code] = set()
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
        self, websocket: WebSocket, room_code: str, player_id: str
    ) -> None:
        async with self._lock:
            if room_code in self._rooms:
                self._rooms[room_code].discard(websocket)
                if not self._rooms[room_code]:
                    del self._rooms[room_code]
                    await self._unsubscribe_from_room(room_code)
            self._players.pop(player_id, None)
        logger.info("websocket_disconnected", room_code=room_code, player_id=player_id)

    async def broadcast_to_room(
        self,
        room_code: str,
        message: WsMessage,
        exclude_player_id: str | None = None,
    ) -> None:
        payload = {"message": message, "exclude_player_id": exclude_player_id}
        try:
            redis_client = get_redis_client()
            channel = f"game:{room_code}"
            await redis_client.publish(channel, json.dumps(payload))
            logger.debug(
                "redis_publish", channel=channel, message_type=message.get("type")
            )
        except Exception as e:
            logger.error("redis_publish_error", error=str(e), room_code=room_code)
            await self._send_to_local_room(room_code, message, exclude_player_id)

    async def send_to_player(self, player_id: str, message: WsMessage) -> None:
        websocket = self._players.get(player_id)
        if websocket:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error("websocket_send_error", player_id=player_id, error=str(e))

    async def _send_to_local_room(
        self,
        room_code: str,
        message: WsMessage,
        exclude_player_id: str | None = None,
    ) -> None:
        connections = self._rooms.get(room_code, set()).copy()
        for websocket in connections:
            player_id = next(
                (pid for pid, ws in self._players.items() if ws == websocket), None
            )
            if exclude_player_id and player_id == exclude_player_id:
                continue
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(
                    "websocket_send_failed", room_code=room_code, error=str(e)
                )

    async def _subscribe_to_room(self, room_code: str) -> None:
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

        self._subscriptions[room_code] = asyncio.create_task(subscriber())

    async def _unsubscribe_from_room(self, room_code: str) -> None:
        task = self._subscriptions.pop(room_code, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("redis_unsubscribed", room_code=room_code)

    def get_local_player_count(self, room_code: str) -> int:
        return len(self._rooms.get(room_code, set()))

    async def close_all(self) -> None:
        for room_code in list(self._subscriptions.keys()):
            await self._unsubscribe_from_room(room_code)
        for connections in self._rooms.values():
            for websocket in connections:
                try:
                    await websocket.close()
                except Exception:
                    pass
        self._rooms.clear()
        self._players.clear()


connection_manager = ConnectionManager()
