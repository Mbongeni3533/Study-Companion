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


def _add_missing_columns() -> None:
    """Additive migration for columns added after a database was created.

    ``create_all`` never alters an existing table, so an upgraded deployment
    would otherwise fail on any newly added column.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    statements: list[str] = []
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            ddl = (
                f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" '
                f"{column.type.compile(dialect=engine.dialect)}"
            )
            default = getattr(column.default, "arg", None)
            if isinstance(default, bool):
                ddl += f" DEFAULT {int(default)}"
            elif isinstance(default, (int, float)):
                ddl += f" DEFAULT {default}"
            elif isinstance(default, str):
                ddl += " DEFAULT '" + default.replace("'", "''") + "'"
            statements.append(ddl)

    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def init_db() -> None:
    """Create any missing tables and columns. Safe to call on every startup."""
    from . import models  # noqa: F401  (registers the models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
