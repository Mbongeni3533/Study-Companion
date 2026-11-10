"""Database engine, session factory and schema bootstrap."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def _build_engine() -> Engine:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    connect_args: dict[str, object] = {}
    if settings.is_sqlite:
        connect_args["check_same_thread"] = False

    engine = create_engine(
        settings.sqlalchemy_url,
        connect_args=connect_args,
        pool_pre_ping=not settings.is_sqlite,
        future=True,
    )

    if settings.is_sqlite:

        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_connection, _record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create any missing tables. Safe to call on every startup."""
    from . import models  # noqa: F401  (registers the models on Base.metadata)

    Base.metadata.create_all(bind=engine)
