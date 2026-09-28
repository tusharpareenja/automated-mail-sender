from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _async_engine():
    settings = get_settings()
    connect_args: dict = {"statement_cache_size": 0}
    if settings.database_ssl:
        connect_args["ssl"] = True
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        connect_args=connect_args,
    )


def _sync_engine():
    settings = get_settings()
    return create_engine(
        settings.database_sync_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


async_engine = None
sync_engine = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None
SyncSessionLocal: sessionmaker[Session] | None = None


def init_engines() -> None:
    global async_engine, sync_engine, AsyncSessionLocal, SyncSessionLocal
    async_engine = _async_engine()
    sync_engine = _sync_engine()
    AsyncSessionLocal = async_sessionmaker(
        async_engine, expire_on_commit=False, autoflush=False
    )
    SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False, autoflush=False)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if AsyncSessionLocal is None:
        init_engines()
    assert AsyncSessionLocal is not None
    return AsyncSessionLocal


def get_sync_session_factory() -> sessionmaker[Session]:
    if SyncSessionLocal is None:
        init_engines()
    assert SyncSessionLocal is not None
    return SyncSessionLocal


async def create_schema() -> None:
    from app import models as _models  # noqa: F401

    if async_engine is None:
        init_engines()
    assert async_engine is not None
    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_sync_db() -> Generator[Session, None, None]:
    session = get_sync_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
