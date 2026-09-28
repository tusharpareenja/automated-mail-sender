import json
import logging
from typing import Any
from uuid import UUID

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def user_channel(user_id: UUID | str) -> str:
    return f"events:user:{user_id}"


def publish_user_event(user_id: UUID | str, payload: dict[str, Any]) -> None:
    """Publish after the event is already persisted. Failures never roll back tracking."""
    try:
        import redis

        settings = get_settings()
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        client.publish(user_channel(user_id), json.dumps(payload, default=str))
        client.close()
    except Exception:
        logger.info("realtime_publish_failed", extra={"event": "realtime_publish_failed"})
