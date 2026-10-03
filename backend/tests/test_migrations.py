"""Migration tests.

`_migrate()` runs against pre-existing databases, so it must be safe on both
SQLite (local/dev) and PostgreSQL (Neon on Render). PostgreSQL is strict about
column types: `ALTER TABLE ... ADD COLUMN is_admin BOOLEAN DEFAULT 0` fails with
"column is of type boolean but default expression is of type integer", while
SQLite happily accepts it. That is why the boolean column is added with no
default literal and its values are written with bound parameters instead — and
why the anti-pattern is guarded statically below.
"""
import inspect as _inspect
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Bind BEFORE importing app.* — whichever module imports app.database first owns
# the engine for the whole test process. Without this, running this module on its
# own would point the app at the developer's real swingtrader.db.
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'migrations.db')}"
os.environ["SECRET_KEY"] = "migration-test-secret-key-longer-than-32-bytes"

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app import database  # noqa: E402


def _legacy_db():
    """A database shaped like a release that predates the current columns."""
    path = os.path.join(tempfile.mkdtemp(), "legacy.db")
    engine = create_engine(f"sqlite:///{path}", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, username VARCHAR(64), "
                "hashed_password VARCHAR(128), is_active BOOLEAN, created_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (id, username, hashed_password, is_active) "
                "VALUES (1, 'admin', 'x', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (id, username, hashed_password, is_active) "
                "VALUES (2, 'member', 'y', 1)"
            )
        )
        conn.execute(
            text(
                # A realistic `signals` table from the previous release: every
                # column that existed before timeframes/outcomes, including the
                # NOT NULL ones the copy has to carry across.
                "CREATE TABLE signals ("
                "id INTEGER PRIMARY KEY, ticker VARCHAR(16) NOT NULL, "
                "date DATE NOT NULL, type VARCHAR(32) NOT NULL, "
                "setup VARCHAR(16), entry FLOAT NOT NULL, target FLOAT NOT NULL, "
                "stop FLOAT NOT NULL, confidence FLOAT NOT NULL, price FLOAT NOT NULL, "
                "sector VARCHAR(64), name VARCHAR(128), "
                "confidence_components JSON, triggered_rules JSON, "
                "event_flags JSON, option_recommendation JSON, "
                "created_at DATETIME NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO signals (id, ticker, date, type, setup, entry, target, stop, "
                "confidence, price, created_at) VALUES "
                "(1, 'AAPL', '2026-01-02', 'PUT', 'LEGACY', 100, 90, 105, 70, 100, "
                "'2026-01-02 12:00:00')"
            )
        )
        conn.execute(text("CREATE TABLE macro_events (id INTEGER PRIMARY KEY)"))
    return engine


class TestMigrations(unittest.TestCase):
    def setUp(self):
        self.engine = _legacy_db()
        self._original = database.engine
        database.engine = self.engine

    def tearDown(self):
        database.engine = self._original
        self.engine.dispose()

    def test_adds_the_missing_columns(self):
        database._migrate()
        insp = inspect(self.engine)
        users = {c["name"] for c in insp.get_columns("users")}
        signals = {c["name"] for c in insp.get_columns("signals")}
        macro = {c["name"] for c in insp.get_columns("macro_events")}
        self.assertIn("is_admin", users)
        self.assertIn("setup", signals)
        self.assertIn("annotation", signals)
        self.assertIn("sentiment", macro)

    def test_backfills_the_oldest_user_as_admin(self):
        database._migrate()
        with self.engine.connect() as conn:
            rows = {
                username: bool(is_admin)
                for username, is_admin in conn.execute(
                    text("SELECT username, is_admin FROM users")
                ).fetchall()
            }
        self.assertTrue(rows["admin"], "the pre-existing account must become an admin")
        self.assertFalse(rows["member"], "other accounts must default to non-admin")

    def test_is_idempotent(self):
        database._migrate()
        database._migrate()  # second run must be a no-op, not an error
        with self.engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        self.assertEqual(count, 2)

    def test_legacy_signal_type_is_migrated(self):
        database._migrate()
        with self.engine.connect() as conn:
            signal_type = conn.execute(text("SELECT type FROM signals")).scalar()
        self.assertEqual(signal_type, "SELL")

    def _migration_source(self, keep_comments: bool = False) -> str:
        source = _inspect.getsource(database._migrate)
        if keep_comments:
            return source
        # Drop comment lines so that documentation *about* an anti-pattern does
        # not trip the guard that looks for the anti-pattern itself.
        return "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )

    def test_no_numeric_default_on_a_boolean_column(self):
        """PostgreSQL rejects `BOOLEAN DEFAULT 0`; SQLite does not. Guard statically."""
        code = self._migration_source().lower()
        self.assertNotIn(
            "boolean default 0",
            code,
            "PostgreSQL rejects an integer default on a BOOLEAN column",
        )
        self.assertNotIn(
            "boolean default 1",
            code,
            "PostgreSQL rejects an integer default on a BOOLEAN column",
        )
        self.assertIn("add column is_admin boolean", code)

    def test_boolean_values_are_written_as_parameters(self):
        """Values for the boolean column must be bound, not inlined as 0/1."""
        code = self._migration_source()
        self.assertIn("SET is_admin = :flag", code)
        self.assertNotIn("SET is_admin = 1", code)
        self.assertNotIn("SET is_admin = 0", code)


if __name__ == "__main__":
    unittest.main()
