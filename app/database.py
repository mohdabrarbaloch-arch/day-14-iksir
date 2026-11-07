"""Database engine and session management.

SQLAlchemy 2.0 style. The engine is created once and shared; sessions are
per-request via the `get_db` dependency. SQLite gets the two pragmas it needs to
behave under concurrency (WAL and a busy timeout), and Postgres is used as-is.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Declarative base for every model."""


def _make_engine(url: str):
    connect_args: dict[str, object] = {}
    if url.startswith("sqlite"):
        # check_same_thread=False is required because FastAPI runs sync
        # dependencies in a threadpool.
        connect_args["check_same_thread"] = False

    engine = create_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that always closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. Import models first so they register on the metadata."""
    from . import models  # noqa: F401  (import for side effect)

    Base.metadata.create_all(bind=engine)
