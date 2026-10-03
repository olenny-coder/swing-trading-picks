"""Configuration tests, focused on database-URL driver normalisation.

Neon/Render hand out bare ``postgresql://`` URLs; SQLAlchemy's default driver for
those varies by version and can raise ``No module named 'psycopg'``. The app
rewrites them to the driver it actually installs.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings  # noqa: E402


class TestDatabaseUrlNormalisation(unittest.TestCase):
    def _url(self, raw: str) -> str:
        # Explicit kwarg wins over any DATABASE_URL in the environment.
        return Settings(database_url=raw).sqlalchemy_database_url

    def test_bare_postgresql_becomes_psycopg2(self):
        self.assertEqual(
            self._url("postgresql://user:pw@ep-x.neon.tech/neondb?sslmode=require"),
            "postgresql+psycopg2://user:pw@ep-x.neon.tech/neondb?sslmode=require",
        )

    def test_heroku_style_postgres_scheme_becomes_psycopg2(self):
        self.assertEqual(
            self._url("postgres://user:pw@host:5432/db"),
            "postgresql+psycopg2://user:pw@host:5432/db",
        )

    def test_explicit_psycopg3_is_rewritten_to_the_installed_driver(self):
        self.assertEqual(
            self._url("postgresql+psycopg://user:pw@host/db"),
            "postgresql+psycopg2://user:pw@host/db",
        )

    def test_already_correct_url_is_untouched(self):
        raw = "postgresql+psycopg2://user:pw@host/db"
        self.assertEqual(self._url(raw), raw)

    def test_sqlite_is_untouched(self):
        raw = "sqlite:///./swingtrader.db"
        self.assertEqual(self._url(raw), raw)

    def test_query_parameters_survive_rewriting(self):
        out = self._url("postgresql://u:p@h/db?sslmode=require&channel_binding=require")
        self.assertTrue(out.startswith("postgresql+psycopg2://"))
        self.assertIn("sslmode=require", out)
        self.assertIn("channel_binding=require", out)

    def test_is_sqlite_flag(self):
        self.assertTrue(Settings(database_url="sqlite:///x.db").is_sqlite)
        self.assertFalse(Settings(database_url="postgresql://u:p@h/db").is_sqlite)

    def test_whitespace_is_tolerated(self):
        self.assertEqual(
            self._url("  postgresql://u:p@h/db  "),
            "postgresql+psycopg2://u:p@h/db",
        )


if __name__ == "__main__":
    unittest.main()
