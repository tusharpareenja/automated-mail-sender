import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.events import user_channel
from app.core.security import decode_token
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/events")
async def events_socket(websocket: WebSocket):
    await websocket.accept()
    token = websocket.query_params.get("token") or websocket.cookies.get("access_token")
    settings = get_settings()
    try:
        if not token:
            await websocket.close(code=4401)
            return
        payload = decode_token(settings, token, "ws")
    except ValueError:
        await websocket.close(code=4401)
        return

    async with get_session_factory()() as db:
        user = await db.scalar(select(User).where(User.id == payload["sub"]))
        if user is None or not user.is_active:
            await websocket.close(code=4401)
            return
        user_id = str(user.id)

    pubsub = None
    redis_client = None
    try:
        import redis.asyncio as redis_async

        redis_client = redis_async.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(user_channel(user_id))
        await websocket.send_json({"data": [{"type": "CONNECTED"}]})
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=20)
            if message and message.get("type") == "message":
                raw = message.get("data")
                event = json.loads(raw) if isinstance(raw, str) else raw
                await websocket.send_json({"data": [event]})
            else:
                await websocket.send_json({"data": [{"type": "PING"}]})
    except WebSocketDisconnect:
        return
    except Exception:
        logger.info("websocket_fallback_poll", extra={"event": "websocket_fallback_poll"})
        try:
            await websocket.send_json({"data": [{"type": "CONNECTED"}]})
            while True:
                await websocket.send_json({"data": [{"type": "PING"}]})
                await asyncio.sleep(10)
        except WebSocketDisconnect:
            return
    finally:
        if pubsub is not None:
            await pubsub.unsubscribe()
            await pubsub.aclose()
        if redis_client is not None:
            await redis_client.aclose()
