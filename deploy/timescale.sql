-- Optional: convert daily_bars into a TimescaleDB hypertable for production
-- time-series performance. Run once after the schema is created.
--
--   psql "$DATABASE_URL" -f deploy/timescale.sql

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- TimescaleDB hypertables require the partitioning column to be part of any
-- unique/primary key, so drop the plain (ticker, date) unique constraint
-- created by SQLAlchemy and replace it with a composite one including date.
ALTER TABLE daily_bars DROP CONSTRAINT IF EXISTS uq_bar_ticker_date;

SELECT create_hypertable('daily_bars', 'date', if_not_exists => TRUE, migrate_data => TRUE);

CREATE INDEX IF NOT EXISTS ix_daily_bars_ticker_date ON daily_bars (ticker, date DESC);
