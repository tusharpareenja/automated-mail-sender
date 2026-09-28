import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router, public_router
from app.core.config import get_settings
from app.core.database import create_schema, init_engines
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.runtime import detect_startup_url, remember_public_url

logger = logging.getLogger("app.request")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    init_engines()
    if get_settings().app_env != "test":
        await create_schema()
    remember_public_url(detect_startup_url())
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    register_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        remember_public_url(str(request.base_url))
        request_id = request.headers.get("x-request-id", uuid4().hex[:12])
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.info(
            "%s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "request_id": request_id,
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
    app.include_router(api_router)
    app.include_router(public_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
