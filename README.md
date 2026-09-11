# Swing Trading Picks

A production-ready swing-trading signal application for **US equities**. It generates daily **buy signals** (trend/momentum breakout and **doji reversal**) and **put-option recommendations**, each with an entry price, target, stop-loss, and a 0–100 confidence rating. Signals are filtered by **macroeconomic developments** and the **earnings calendar**, and the whole app is **fully responsive** (desktop + mobile).

> **Zero-config demo:** the app ships with a deterministic *mock* data provider, so it runs end-to-end (dashboard, charts, settings, backtesting) with **no API keys**. Add your **Alpaca** credentials to switch to live/paper market data.

---

## Features

- **Three signal types**
  - `BUY_STANDARD` — trend/momentum breakout above the 20-day high.
  - `BUY_DOJI_REVERSAL` — doji after a downtrend, confirmed by a bullish reversal bar.
  - `SELL` — bearish breakdown, traded via **liquid put options** (never shorting).
- **Confidence scoring** — weighted sum of technical confluence (40%), backtest performance (20%), regime alignment (15%), sector strength (10%), volume (5%), and macro/earnings risk (10%), labeled Low/Medium/High.
- **Macro & event filtering** — market regime (SPY vs 200-day MA, VIX, yield curve), sector rotation, interest-rate sensitivity, earnings-proximity suppression, and high-impact-event confidence adjustment.
- **API key management** — enter/update Alpaca (paper/live) and optional Finnhub/Polygon/FRED keys from the UI; keys are **encrypted at rest** (Fernet), **masked** in the UI, never sent to the browser, and fall back to environment variables.
- **Responsive dashboard** — top-20 shortlist (with sector diversity), summary cards, filters, macro/earnings widgets, and interactive charts (TradingView Lightweight Charts) with a doji highlight and options chain.
- **Backtesting** — event-aware replay with win rate, avg return, max drawdown, profit factor, Sharpe, and walk-forward-capable CLI.
- **Scheduling** — APScheduler daily jobs (ingestion, macro, signal generation), plus a GitHub Actions cron entrypoint.
- **Public read / admin control** — the daily view, history, macro dashboard, and charts are **readable without logging in**; only the admin (signed-in) can refresh data or change API keys/settings.
- **Collapsible sections & hamburger nav** — every major section can be expanded/collapsed, the header carries a hamburger menu at all screen sizes, and each signal page ends with a **"How confidence was derived"** breakdown showing the weighted sub-score math.

---

## Access model

| Area | Public (no login) | Admin (logged in) |
|---|---|---|
| Daily view, History, Macro, Charts | ✅ view | ✅ view |
| Refresh data button | — | ✅ |
| Settings / API keys | — | ✅ |

Sign in at `/login` (default `admin` / `changeme`) to refresh data or manage keys.

---

## Architecture

```
┌──────────────────────────┐      ┌──────────────────────────────┐
│  Frontend (Next.js 14)    │      │  Backend (FastAPI)            │
│  React + Tailwind + LWC   │ /api │  signal engine · confidence   │
│  responsive, mobile-first │─────▶│  macro/earnings filters       │
└──────────────────────────┘      │  encrypted API-key storage    │
                                  └──────────────┬───────────────┘
                                                 │ adapters
                          ┌──────────────────────┼───────────────────────┐
                          ▼                      ▼                       ▼
                     Alpaca (httpx)      Finnhub / FRED / Polygon     MOCK (demo)
                          └──────────────────────┬───────────────────────┘
                                                 ▼
                                PostgreSQL + TimescaleDB (or SQLite for demo)
```

- **Backend:** FastAPI + SQLAlchemy 2.0 + Pydantic v2. Provider adapters (`MarketDataProvider`, `MacroDataProvider`) make every data source pluggable.
- **Database:** SQLite by default (zero-config demo/tests); PostgreSQL + TimescaleDB in production (see `deploy/timescale.sql`).
- **Frontend:** Next.js 14 App Router + Tailwind CSS + Lightweight Charts, proxying `/api/*` to the backend (no CORS, backend URL stays server-side).

---

## Quickstart (demo, no keys)

**One command (Windows):** double-click `start.cmd` (or run `.\start.cmd`). It launches the backend and frontend in separate windows and opens the app. First boot seeds demo data, so wait for `Application startup complete` in the backend window before signing in (`admin` / `changeme`).

To run the two halves manually — requires Python 3.11+ and Node 20+:

```bash
cd backend
python -m pip install -r requirements.txt

# Optional: copy and edit configuration
cp ../.env.example .env

# Run (auto-creates the DB, seeds mock data, starts the API)
uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs** for the interactive API. The app seeds mock data on first boot, so the daily view is populated immediately.

Then start the frontend (requires Node 20+):

```bash
cd frontend
npm install
cp .env.local.example .env.local   # API_URL=http://localhost:8000
npm run dev
```

Open **http://localhost:3000**. Sign in with the default single-user credentials (`admin` / `changeme`, configurable via `ADMIN_USERNAME` / `ADMIN_PASSWORD`).

### Default demo credentials

| Setting | Default |
|---|---|
| Username | `admin` |
| Password | `changeme` |

**Change the password and `SECRET_KEY` before any non-local deployment.**

---

## Connecting Alpaca (real market data)

1. Get API keys from [Alpaca](https://alpaca.markets) (Paper keys recommended to start).
2. Either set environment variables, or (recommended) enter them in the app:
   - **Settings → Alpaca** — paste the API key and secret, keep *Paper trading* checked, and click **Save**, then **Test connection**.
3. Keys entered via the UI are **encrypted at rest** with a Fernet key derived from `SECRET_KEY` and take precedence over environment variables. The browser only ever sees masked values (`AK************1234`).
4. Click **↻ Refresh data** on the Daily View to pull real Alpaca bars and regenerate signals (this replaces the seeded demo data). A scheduled pull runs automatically every day at **8:30 PM Singapore time (12:30 UTC)**.

Environment-variable alternative:

```bash
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_PAPER=true            # false for live
DATA_PROVIDER=auto           # auto | alpaca | polygon | mock
```

Optional macro/options providers (all optional; MOCK fills gaps when absent):

```bash
FINNHUB_API_KEY=...   # economic + earnings calendars
FRED_API_KEY=...      # 10Y yield, Fed Funds, VIX
POLYGON_API_KEY=...   # alternative bars / options chain
```

---

## Signal engine reference

| Criterion | BUY_STANDARD | BUY_DOJI_REVERSAL | SELL |
|---|---|---|---|
| Trend | price > EMA50, EMA20 > EMA50 | doji after downtrend (price < EMA20) | price < EMA50, EMA20 < EMA50 |
| Momentum | MACD bullish cross ≤3 bars | bullish confirmation bar | MACD bearish cross ≤3 bars |
| Oscillator | RSI 40–72 | — | RSI 28–60 |
| Volume | > 1.5× avg | > 1.2× avg | > 1.5× avg |
| Break | close > 20-day high | dips below doji low, closes above it in upper half | close < 20-day low |
| Entry | close | doji low + $0.01 | close (put strike near-the-money) |
| Stop | swing low / 1.5×ATR | swing low or 1.5×ATR | 1.5×ATR above |
| Target | 2.5×ATR / resistance | 2–3×ATR / resistance | 2.5×ATR below |

> Signals are **score-based**: a candidate only needs a minimum confluence (≥3 of 6 conditions) to surface, so real market data always produces a ranked shortlist. Confidence scales with how many conditions are met — low-confluence setups still appear, just with a lower (Low/Medium) confidence. The RSI bands are tunable module constants in `backend/app/core/signal_engine.py`.

**Macro / event filtering** (applied to every signal): earnings within 7 days suppress the signal unless confidence > 80 and the user opted into earnings plays; high-impact events within 2 trading days reduce confidence 10–20 points; regime/sector rotation bias confidence by signal direction; rate-sensitive sectors are penalized when the 10-year yield is rising sharply; and the **economic calendar's net sentiment** (positive/negative/neutral) nudges confidence up or down by up to 15 points.

**Macro data** comes from **Yahoo Finance** (real SPY vs 200-day MA, VIX, 10-year yield, and sector-ETF relative strength) via `httpx` — no key required — with FRED/Finnhub (optional keys) and the built-in MOCK provider as fallbacks. Stock prices/signals continue to use **Alpaca**.

---

## Running the tests

The backend test suite uses the standard library `unittest` runner (no extra deps).

```bash
cd backend
python -m unittest discover -s tests -t .
```

---

## Backtesting

```bash
cd backend
python scripts/run_backtest.py --years 2 --strategy all
python scripts/run_backtest.py --years 5 --tickers AAPL MSFT NVDA --strategy BUY_DOJI_REVERSAL
```

Writes `reports/backtest.md` and `reports/backtest.json`. A sample report (generated on MOCK synthetic data as a pipeline sanity check — **not** real strategy validation) is at `backend/reports/backtest.md`. For meaningful results, run it against real Alpaca history (set your keys, then run with `--years 5` or more).

---

## Deployment

**Free cloud deployment:** see **[`docs/deployment.md`](docs/deployment.md)** for a
step-by-step **free-tier** guide (Vercel + Render + Neon + GitHub Actions cron).

### Docker Compose (full stack: Postgres+TimescaleDB, backend, frontend)

```bash
docker compose up --build
# frontend: http://localhost:3000 · backend: http://localhost:8000
```

### Vercel (frontend) + Render (backend) + managed Postgres

1. **Backend** → Render: deploy the repo with root directory `backend` (Docker). Set `DATABASE_URL`, `SECRET_KEY`, `DISABLE_SCHEDULER=true`, and provider keys as Render variables.
2. **Frontend** → Vercel: import the repo with root directory `frontend`; set `API_URL` to your Render backend URL (Vercel auto-detects `frontend/vercel.json`).
3. **Database** → Neon/Supabase (free Postgres). Optionally run `deploy/timescale.sql` to enable the hypertable.
4. **Cron** → enable the `.github/workflows/daily-cron.yml` workflow (free) and set the repository secrets (`DATABASE_URL`, `SECRET_KEY`, provider keys). Set `DISABLE_SCHEDULER=true` on Render so it doesn't double-run.

---

## Project structure

```
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers (auth, settings, signals, macro, backtest)
│   │   ├── core/           # indicators, signal engine, confidence, regime, backtest
│   │   ├── providers/      # Alpaca / Finnhub / FRED / Polygon / MOCK adapters
│   │   ├── services/       # credentials, data ingestion, macro, signals, options
│   │   ├── tasks/          # APScheduler jobs
│   │   ├── models.py       # SQLAlchemy models
│   │   ├── schemas.py      # Pydantic schemas
│   │   └── main.py         # FastAPI app
│   ├── scripts/            # backtest CLI + CI jobs entrypoint
│   └── tests/              # unittest suite
├── frontend/
│   ├── app/                # pages (daily, history, macro, settings, login, detail)
│   ├── components/         # responsive UI + Lightweight Charts
│   └── lib/                # API client, auth context, types
├── deploy/timescale.sql
├── docker-compose.yml
├── railway.toml
├── frontend/vercel.json
└── .github/workflows/daily-cron.yml
```

## Configuration reference

See `.env.example` for the full list. Key variables: `SECRET_KEY`, `DATABASE_URL`, `DATA_PROVIDER`, `ALPACA_*`, `FINNHUB_API_KEY`, `FRED_API_KEY`, `POLYGON_API_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `CORS_ORIGINS`, and the `CRON_*` schedules.

---

## Security notes

- API keys are Fernet-encrypted at rest (key derived from `SECRET_KEY`) and never serialized to the frontend; responses carry masked values only.
- Passwords are bcrypt-hashed; authentication uses short-lived JWT bearer tokens.
- Use HTTPS in production, a strong `SECRET_KEY`, and change the default admin password.

## Disclaimer

This software is for educational and informational purposes only. It is **not** financial advice. Trading securities and options involves substantial risk of loss. Always do your own research.
