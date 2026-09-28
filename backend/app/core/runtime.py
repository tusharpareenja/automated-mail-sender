import logging
import sys

from app.core.config import get_settings

logger = logging.getLogger(__name__)

REDIS_KEY = "runtime:api_base_url"
_DEFAULT = "http://127.0.0.1:8000"


def detect_startup_url() -> str:
    host = "127.0.0.1"
    port = 8000
    args = sys.argv
    if "--host" in args:
        raw_host = args[args.index("--host") + 1]
        if raw_host not in {"0.0.0.0", "::", "[::]"}:
            host = raw_host
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    return f"http://{host}:{port}"


def remember_public_url(url: str) -> None:
    value = url.rstrip("/")
    if is_local_url(value):
        return
    try:
        import redis

        client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
        client.set(REDIS_KEY, value)
        client.close()
    except Exception:
        logger.info("runtime_url_store_failed", extra={"event": "runtime_url_store_failed"})


def untrusted_tracking_host(url: str) -> bool:
    """Temporary tunnels and local hosts look like phishing links to mailbox filters."""
    from urllib.parse import urlparse

    host = (urlparse(url or "").hostname or "").lower()
    if not host or is_local_url(url):
        return True
    return (
        host.endswith("trycloudflare.com")
        or host.endswith("ngrok.io")
        or host.endswith("ngrok-free.app")
        or host.endswith("loca.lt")
    )


def is_local_url(url: str) -> bool:
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local")


def get_public_url() -> str:
    configured = (get_settings().tracking_public_url or "").strip().rstrip("/")
    if configured:
        return configured
    try:
        import redis

        client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
        stored = client.get(REDIS_KEY)
        client.close()
        if stored:
            return str(stored).rstrip("/")
    except Exception:
        pass
    return detect_startup_url() or _DEFAULT
