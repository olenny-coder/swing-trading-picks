"""Database engine, session factory, and declarative base.

SQLite is the zero-config default (used by the MOCK demo and the test suite);
PostgreSQL (optionally with TimescaleDB) is used in production. The same
SQLAlchemy models work against both.
"""
from __future__ import annotations

import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

logger = logging.getLogger("app.database")

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

    logger.info("initialising database (%s)", engine.dialect.name)
    Base.metadata.create_all(bind=engine)
    _migrate()
    logger.info("database ready")


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
                # Add the column with NO default literal: `BOOLEAN DEFAULT 0` is
                # rejected by PostgreSQL ("column is of type boolean but default
                # expression is of type integer") even though SQLite tolerates it.
                # Values are then written with bound parameters, so the driver
                # picks the correct literal for the dialect.
                conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN"))
                conn.execute(
                    text("UPDATE users SET is_admin = :flag"), {"flag": False}
                )
                # The pre-existing (bootstrap) account becomes the first admin.
                conn.execute(
                    text(
                        "UPDATE users SET is_admin = :flag WHERE id = "
                        "(SELECT MIN(id) FROM users)"
                    ),
                    {"flag": True},
                )

    if "signals" in tables:
        cols = {c["name"] for c in insp.get_columns("signals")}
        if "timeframe" not in cols or "outcome" not in cols:
            # The unique key now includes `timeframe`, so the table has to change
            # shape. PostgreSQL does that additively; SQLite cannot drop a
            # constraint in place and rebuilds instead.
            _upgrade_signals_table(cols)

        # Re-reflect: the rebuild above replaced the table, and SQLAlchemy's
        # inspector caches its reflection.
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("signals")}
        if "setup" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE signals ADD COLUMN setup VARCHAR(16) DEFAULT 'LEGACY'")
                )
            logger.info("added signals.setup")
        if "annotation" not in cols:
            # LLM research agent output (JSON: sentiment, risk flags, delta).
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE signals ADD COLUMN annotation JSON"))
            logger.info("added signals.annotation")
        # Collapse legacy signal types onto the BUY/SELL direction model.
        with engine.begin() as conn:
            conn.execute(text("UPDATE signals SET type = 'SELL' WHERE type = 'PUT'"))
            conn.execute(
                text("UPDATE signals SET type = 'BUY' WHERE type IN ('BUY_STANDARD', 'BUY_DOJI_REVERSAL')")
            )
            conn.execute(
                text("UPDATE signals SET setup = 'LEGACY' WHERE setup IS NULL OR setup = ''")
            )
            conn.execute(
                text("UPDATE signals SET timeframe = 'DAILY' WHERE timeframe IS NULL OR timeframe = ''")
            )


#: Columns the timeframe/outcome release added, with the DDL to add each one.
_ADDITIVE_SIGNAL_COLUMNS: dict[str, str] = {
    "timeframe": "ALTER TABLE signals ADD COLUMN timeframe VARCHAR(8)",
    "outcome": "ALTER TABLE signals ADD COLUMN outcome JSON",
    "setup": "ALTER TABLE signals ADD COLUMN setup VARCHAR(16)",
    "annotation": "ALTER TABLE signals ADD COLUMN annotation JSON",
}

_UNIQUE_KEY_NAME = "uq_signal_ticker_date_setup_timeframe"


def _upgrade_signals_table(existing_columns: set[str]) -> None:
    """Bring the ``signals`` table up to the current schema.

    PostgreSQL gets a purely **additive** upgrade — ALTER columns, backfill, swap
    the unique key — which moves no data and never drops the table. SQLite cannot
    drop a constraint in place, so it rebuilds. If the PostgreSQL path fails for
    any reason it rolls back and the rebuild is tried instead.
    """
    logger.info("upgrading the signals table for the timeframe/outcome schema")
    if engine.dialect.name == "postgresql":
        try:
            _upgrade_signals_postgres(existing_columns)
            logger.info("signals table upgraded additively")
            return
        except Exception:
            logger.exception("additive signals upgrade failed; rebuilding the table instead")
    _rebuild_signals_table(existing_columns)


def _upgrade_signals_postgres(existing_columns: set[str]) -> None:
    """Additive PostgreSQL upgrade: no table rebuild, no data movement."""
    from sqlalchemy import text

    with engine.begin() as conn:
        for name, ddl in _ADDITIVE_SIGNAL_COLUMNS.items():
            if name not in existing_columns:
                conn.execute(text(ddl))

        conn.execute(
            text("UPDATE signals SET timeframe = 'DAILY' WHERE timeframe IS NULL OR timeframe = ''")
        )
        conn.execute(
            text("UPDATE signals SET setup = 'LEGACY' WHERE setup IS NULL OR setup = ''")
        )
        # Collapse legacy signal types onto the BUY/SELL direction model.
        conn.execute(text("UPDATE signals SET type = 'SELL' WHERE type = 'PUT'"))
        conn.execute(
            text(
                "UPDATE signals SET type = 'BUY' "
                "WHERE type IN ('BUY_STANDARD', 'BUY_DOJI_REVERSAL')"
            )
        )

        # Swap the unique key. The old one omitted `timeframe`, so the same setup
        # could not exist on two intervals for one ticker.
        names = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT c.conname FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "WHERE t.relname = 'signals' AND c.contype = 'u'"
                )
            ).fetchall()
        ]
        for name in names:
            if name != _UNIQUE_KEY_NAME:
                conn.execute(text(f'ALTER TABLE signals DROP CONSTRAINT "{name}"'))
        if _UNIQUE_KEY_NAME not in names:
            conn.execute(
                text(
                    f"ALTER TABLE signals ADD CONSTRAINT {_UNIQUE_KEY_NAME} "
                    "UNIQUE (ticker, date, setup, timeframe)"
                )
            )

        conn.execute(text("ALTER TABLE signals ALTER COLUMN timeframe SET NOT NULL"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_signal_timeframe_date "
                "ON signals (timeframe, date)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_signal_date_confidence "
                "ON signals (date, confidence)"
            )
        )


def _rebuild_signals_table(existing_columns: set[str]) -> None:
    """Recreate ``signals`` with the current schema, copying existing rows.

    The unique key now includes ``timeframe``, and SQLite cannot drop a
    constraint in place, so the table has to be rebuilt. Existing rows are copied
    across and stamped DAILY, which preserves the pick history the accuracy view
    reads.

    Everything happens on **one connection inside one transaction**. The old
    table is set aside with ``CREATE TABLE ... AS SELECT`` (which deliberately
    copies no indexes or constraints, releasing the old index names for the new
    table), the replacement is created, populated, and only then is the copy
    dropped. If any step fails the whole transaction rolls back, so the original
    ``signals`` table is still there — a failed migration can never leave the
    service without one.
    """
    from sqlalchemy import text

    from .models import Signal

    table = Signal.__table__
    # Only copy columns that exist in the old table, in the new table's order.
    copy_columns = [
        column.name
        for column in table.columns
        if column.name not in ("timeframe", "outcome") and column.name in existing_columns
    ]
    # Quote identifiers: `open`/`high`/`index` style names are reserved words on
    # some dialects.
    collist = ", ".join(f'"{name}"' for name in copy_columns)

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS signals_backup"))
        conn.execute(text("CREATE TABLE signals_backup AS SELECT * FROM signals"))
        conn.execute(text("DROP TABLE signals"))
        # Same connection, so the new table is visible to the statements below.
        table.create(bind=conn)
        if copy_columns:
            conn.execute(
                text(
                    f'INSERT INTO signals ({collist}, timeframe) '
                    f"SELECT {collist}, 'DAILY' FROM signals_backup"
                )
            )
        conn.execute(text("DROP TABLE signals_backup"))
    logger.info("rebuilt the signals table for the timeframe/outcome schema")
