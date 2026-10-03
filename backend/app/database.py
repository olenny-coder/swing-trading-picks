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
    settings.sqlalchemy_database_url,
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
    tables = set(insp.get_table_names())

    if "macro_events" in tables:
        cols = {c["name"] for c in insp.get_columns("macro_events")}
        if "sentiment" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE macro_events ADD COLUMN sentiment VARCHAR(16) DEFAULT 'neutral'")
                )

    if "users" in tables:
        cols = {c["name"] for c in insp.get_columns("users")}
        if "is_admin" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")
                )
                # The pre-existing (bootstrap) account becomes the first admin.
                conn.execute(
                    text(
                        "UPDATE users SET is_admin = 1 WHERE id = "
                        "(SELECT MIN(id) FROM users)"
                    )
                )

    if "signals" in tables:
        cols = {c["name"] for c in insp.get_columns("signals")}
        if "setup" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE signals ADD COLUMN setup VARCHAR(16) DEFAULT 'LEGACY'")
                )
        if "annotation" not in cols:
            # LLM research agent output (JSON: sentiment, risk flags, delta).
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE signals ADD COLUMN annotation JSON"))
        # Collapse legacy signal types onto the BUY/SELL direction model.
        with engine.begin() as conn:
            conn.execute(text("UPDATE signals SET type = 'SELL' WHERE type = 'PUT'"))
            conn.execute(
                text("UPDATE signals SET type = 'BUY' WHERE type IN ('BUY_STANDARD', 'BUY_DOJI_REVERSAL')")
            )
            conn.execute(
                text("UPDATE signals SET setup = 'LEGACY' WHERE setup IS NULL OR setup = ''")
            )
