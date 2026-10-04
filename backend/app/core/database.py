"""SQLAlchemy async engine, session factory and declarative base."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.config import settings as global_settings

# Alembic autogenerate compares against this; renaming an entry requires a
# manual migration.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def as_dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


def build_engine(settings: Settings) -> AsyncEngine:
    """Create the async engine.

    Under pytest every test runs on a fresh event loop, and a pooled connection
    belongs to the loop that opened it. `TESTING` therefore switches to
    NullPool so a connection is never reused across loops.
    """
    import os

    if os.getenv("TESTING", "").lower() in {"1", "true", "yes"}:
        return create_async_engine(
            settings.async_database_url,
            echo=settings.db_echo,
            poolclass=NullPool,
            future=True,
        )
    return create_async_engine(
        settings.async_database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        future=True,
    )


engine: AsyncEngine = build_engine(global_settings)
async_session_factory = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
