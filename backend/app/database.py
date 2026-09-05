"""Database engine, session factory, and declarative base.

SQLite is the zero-config default (used by the MOCK demo and the test suite);
PostgreSQL (optionally with TimescaleDB) is used in production. The same
SQLAlchemy models work against both.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()

_connect_args: dict = {}
if settings.is_sqlite:
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

if settings.is_sqlite:
    # WAL mode + a busy timeout let the background refresh thread write while
    # request threads read/write, avoiding "database is locked" errors.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db():
    """FastAPI dependency yielding a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Imported models must be registered first."""
    from . import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    """Lightweight additive migrations for pre-existing databases."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "macro_events" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("macro_events")}
    if "sentiment" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE macro_events ADD COLUMN sentiment VARCHAR(16) DEFAULT 'neutral'")
            )
