# Swing Trading Picks

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-33%20passing-brightgreen.svg)](backend/tests)

> **Topics:** `swing-trading` · `trading-signals` · `stock-screener` · `technical-analysis` · `sma` · `breakout` · `put-options` · `alpaca` · `fastapi` · `nextjs` · `tailwindcss` · `lightweight-charts` · `backtesting` · `fintech` · `quant`

A production-ready swing-trading signal application for **US equities**. It scans daily charts with the **SMA 20/50 flow system** for eight high-probability continuation and reversal setups (UC1, UC2, DC1, DC2, UR1, DR1, UR2, DR2), each with an entry price, target, stop-loss, and a 0–100 confidence rating. Signals are filtered by **macroeconomic developments** and the **earnings calendar**, and the whole app is **fully responsive** (desktop + mobile).

> **Zero-config demo:** the app ships with a deterministic *mock* data provider, so it runs end-to-end (dashboard, charts, settings, backtesting) with **no API keys**. Add your **Alpaca** credentials to switch to live/paper market data.

---

## Features

- **Eight setups from the SMA 20/50 flow system** (see [Signal engine reference](#signal-engine-reference))
  - Continuation: `UC1` / `UC2` (bullish, shallow / deep pullback), `DC1` / `DC2` (bearish).
  - Reversal: `UR1` (early upside), `DR1` (early downside), `UR2` (double top), `DR2` (double bottom).
  - Each setup is confirmed by an **EXE** (momentum entry candle) closing beyond the **LP** (liquidity point) within a 5–6 bar time limit; bearish setups are traded via **liquid put options** (never shorting).
- **Confidence scoring** — weighted sum of technical confluence (40%), backtest performance (20%), regime alignment (15%), sector strength (10%), volume (5%), and macro/earnings risk (10%), labeled Low/Medium/High.
- **Macro & event filtering** — market regime (SPY vs 200-day MA, VIX, yield curve), sector rotation, interest-rate sensitivity, earnings-proximity suppression, and high-impact-event confidence adjustment.
- **API key management** — enter/update Alpaca (paper/live) and optional Finnhub/Polygon/FRED keys from the UI; keys are **encrypted at rest** (Fernet), **masked** in the UI, never sent to the browser, and fall back to environment variables.
- **Responsive dashboard** — top-20 shortlist (with sector diversity), per-setup counters, filters (direction + setup), macro/earnings widgets, and interactive charts (TradingView Lightweight Charts) with an options chain.
- **Backtesting** — event-aware replay with win rate, avg return, max drawdown, profit factor, Sharpe, and walk-forward-capable CLI.
- **Scheduling** — APScheduler daily jobs (ingestion, macro, signal generation), plus a GitHub Actions cron entrypoint.
- **Public read / admin control** — the daily view, history, macro dashboard, and charts are **readable without logging in**; only the admin (signed-in) can refresh data or change API keys/settings.
- **Collapsible sections & hamburger nav** — every major section can be expanded/collapsed, the header carries a hamburger menu at all screen sizes, and each signal page ends with a **"How confidence was derived"** breakdown showing the weighted sub-score math.
- **One-service deployment** — FastAPI serves both the API and the exported frontend, so the app runs on **Render + Neon with no Vercel and no Node server**.

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

The engine is the **SMA 20/50 flow system**: daily bars only, market context first, then a
structural trigger. Definitions:

| Term | Meaning |
|---|---|
| **Flow** | *Positive* when price is above the 50 SMA, *Negative* when below it. |
| **EXE** | Entry Execution — a strong momentum candle closing beyond a level (bullish candle for longs, bearish for shorts). |
| **LP** | Liquidity Point — the structural level used as the trigger (a swept swing low for longs, a swept swing high for shorts). |
| **Flush bar** | A large aggressive momentum candle in the trend direction (range ≥ 1.4×ATR, body ≥ 55% of range). |
| **MF** | Majority Flush — at least 2 flush bars within the last 3. |
| **Time limit** | The confirming EXE must appear within 5–6 bars or the setup is invalidated. |
| **Risk** | Stop just beyond the structural invalidation point; target projected from the risk-reward ratio. |

### Setups

| Code | Direction | Context | Trigger |
|---|---|---|---|
| `UC1` | BUY | Positive flow, shallow pullback holding above the 50 SMA | Bullish EXE closes at/above the LP within 6 bars |
| `UC2` | BUY | Positive flow, deeper pullback that tested the 50 SMA | As above, with room left to the prior impulse high |
| `DC1` | SELL | Negative flow, shallow pullback holding below the 50 SMA | Bearish EXE closes at/below the LP within 6 bars |
| `DC2` | SELL | Negative flow, deeper pullback that tested the 50 SMA | As above |
| `UR1` | BUY | Sideways range, downside flush forces liquidity | Bullish EXE within 6 bars closing at/above the LP |
| `DR1` | SELL | Sideways range, majority flush forms liquidity | Bearish EXE closing at/below the LP (no bar count) |
| `UR2` | SELL | Double top in an up-flow, "bigger retracement" | Bearish EXE closes at/below the LP (the peak) |
| `DR2` | BUY | Double bottom in a down-flow, majority flush | Bullish EXE within 5 bars closing at/above the LP (neckline) |

| Exit | Rule |
|---|---|
| Target | `entry ± RR × risk`, with per-setup RR of 2.0 (UC1/DC1/UR1/DR1), 2.5 (UC2/DC2) and 3.0 (UR2/DR2) |
| Stop | Just beyond the structural point (pullback extreme / flush extreme), plus a 0.25×ATR buffer |
| Guardrail | Setups whose structural stop is further than 15% from entry are dropped as untradeable |

> Thresholds are explicit, tunable constants at the top of `backend/app/core/sma_strategy.py`
> (`MOMENTUM_BODY_RATIO`, `FLUSH_ATR_MIN`, `MAX_SETUP_BARS`, `SETUP_RR`, `MAX_RISK_PCT`, …).
> The source rules are discretionary, so each one is documented at its implementation site.

**Macro / event filtering** (applied to every signal): earnings within 7 days suppress the signal unless confidence > 80 and the user opted into earnings plays; high-impact events within 2 trading days reduce confidence 10–20 points; regime/sector rotation bias confidence by signal direction; rate-sensitive sectors are penalized when the 10-year yield is rising sharply; and the **economic calendar's net sentiment** (positive/negative/neutral) nudges confidence up or down by up to 15 points.

**Macro data** comes from **Yahoo Finance** (real SPY vs 200-day MA, VIX, 10-year yield, and sector-ETF relative strength) via `httpx` — no key required — with FRED/Finnhub (optional keys) and the built-in MOCK provider as fallbacks. Stock prices/signals continue to use **Alpaca**.

---

## Deploying on Render + Neon (no Vercel)

The frontend is a **static export** and FastAPI serves it at `/`, so the whole app is a
**single service**. `render.yaml` is a ready blueprint:

1. Push this repo to GitHub.
2. Create a free Postgres at **[neon.tech](https://neon.tech)** and copy the connection string,
   inserting `+psycopg2` after `postgresql`, e.g.
   `postgresql+psycopg2://user:pass@ep-xxx.aws.neon.tech/neondb?sslmode=require`
3. Render → **New → Blueprint** → pick the repo (it reads `render.yaml`), then fill in the
   prompted secrets: `DATABASE_URL`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ADMIN_PASSWORD`.
4. Render builds the Docker image (Node builds the UI, Python stage serves it) and gives you
   `https://<service>.onrender.com` — that **single URL is the whole app** (`/api/health` for
   the health check, `/docs` for the API).
5. Because free instances sleep, `DISABLE_SCHEDULER=true`; the daily 8:30 PM SGT pull runs from
   `.github/workflows/daily-cron.yml` (add your Render URL + `SECRET_KEY` as repo secrets).

Local production check: `docker compose up --build` → <http://localhost:8000>.

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

**Recommended (free, one service):** **[Render + Neon](#deploying-on-render--neon-no-vercel)** — `render.yaml`
is a ready blueprint, no Vercel and no separate frontend host. See also
**[`docs/deployment.md`](docs/deployment.md)** for the longer step-by-step walkthrough.

### Docker Compose (app + Postgres/TimescaleDB)

```bash
docker compose up --build
# whole app (UI + API): http://localhost:8000
```

### Split hosting (optional)

If you prefer separate hosts, the frontend is still self-contained:

1. **Backend** → any Docker host: `backend/Dockerfile` is an API-only image. Set `DATABASE_URL`,
   `SECRET_KEY`, `DISABLE_SCHEDULER=true`, and provider keys.
2. **Frontend** → any static host: build with `NEXT_PUBLIC_API_BASE=https://your-api-host`
   (`frontend/Dockerfile` produces an nginx image, or serve `frontend/out` from a CDN).
3. **Database** → Neon/Supabase (free Postgres). Optionally run `deploy/timescale.sql` to enable the hypertable.
4. **Cron** → enable `.github/workflows/daily-cron.yml` (free) and set the repository secrets (`DATABASE_URL`, `SECRET_KEY`, provider keys, `API_BASE_URL`). Keep `DISABLE_SCHEDULER=true` on hosts that sleep.

---

## Project structure

```
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers (auth, settings, signals, macro, backtest, refresh)
│   │   ├── core/           # sma_strategy (setup engine), indicators, confidence, regime, backtest
│   │   ├── providers/      # Alpaca / Finnhub / FRED / Polygon / Yahoo / MOCK adapters
│   │   ├── services/       # credentials, data ingestion, macro, signals, options, refresh
│   │   ├── tasks/          # APScheduler jobs
│   │   ├── models.py       # SQLAlchemy models
│   │   ├── schemas.py      # Pydantic schemas
│   │   └── main.py         # FastAPI app (also serves the exported frontend)
│   ├── scripts/            # backtest CLI + CI jobs entrypoint
│   └── tests/              # unittest suite
├── frontend/
│   ├── app/                # static-exported pages (daily, history, macro, settings, login, signals)
│   ├── components/         # responsive UI + Lightweight Charts
│   ├── public/logo.svg     # aligned logo mark + wordmark
│   └── lib/                # API client, auth context, types
├── Dockerfile              # multi-stage: builds the UI, serves UI + API (Render)
├── render.yaml             # Render blueprint (single service)
├── deploy/timescale.sql
├── docker-compose.yml
├── .github/workflows/daily-cron.yml
└── LICENSE
```

## Configuration reference

See `.env.example` for the full list. Key variables: `SECRET_KEY`, `DATABASE_URL`, `DATA_PROVIDER`, `ALPACA_*`, `FINNHUB_API_KEY`, `FRED_API_KEY`, `POLYGON_API_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `CORS_ORIGINS`, and the `CRON_*` schedules.

---

## Security notes

- API keys are Fernet-encrypted at rest (key derived from `SECRET_KEY`) and never serialized to the frontend; responses carry masked values only.
- Passwords are bcrypt-hashed; authentication uses short-lived JWT bearer tokens.
- Use HTTPS in production, a strong `SECRET_KEY`, and change the default admin password.

---

## License

Released under the **[MIT License](LICENSE)** — free to use, modify, and distribute, provided the copyright notice and permission notice are retained.

> **Why MIT?** It's the simplest permissive license and the norm for tools like this. If you plan to accept corporate contributions or want an explicit patent grant, **[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)** is the better alternative (it adds a patent grant and trademark clause). Avoid GPL here unless you want to force derivatives to stay open.

## Disclaimer

This software is for educational and informational purposes only. It is **not** financial advice. Trading securities and options involves substantial risk of loss. Always do your own research.
