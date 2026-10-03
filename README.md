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
- **Blended confidence** — a rating built from two factor groups: **continuation factors** (trend strength, MA alignment, pullback control, clean structure, trigger quality, participation) blended with **reversal factors** (flush intensity, liquidity sweep, reversal trigger, exhaustion, pattern quality), then adjusted for regime, sector rotation and a **counter impact** term. Labeled Low/Medium/High. See [How confidence is derived](#how-confidence-is-derived).
- **Macro & event filtering** — market regime (SPY vs 200-day MA, VIX, yield curve), sector rotation, interest-rate sensitivity, earnings-proximity suppression, and high-impact-event confidence adjustment.
- **API key management** — enter/update Alpaca (paper/live) and optional Finnhub/Polygon/FRED keys from the UI; keys are **encrypted at rest** (Fernet), **masked** in the UI, never sent to the browser, and fall back to environment variables.
- **Responsive dashboard** — top-20 shortlist (with sector diversity), per-setup counters, filters (direction + setup), macro/earnings widgets, and interactive charts (TradingView Lightweight Charts) with an options chain.
- **Backtesting** — event-aware replay with win rate, avg return, max drawdown, profit factor, Sharpe, and walk-forward-capable CLI.
- **Scheduling** — APScheduler daily jobs (ingestion, macro, signal generation), plus a GitHub Actions cron entrypoint.
- **Public read / admin control** — the daily view, history, macro dashboard, and charts render **without logging in**, but anonymous visitors only ever receive a **synthetic DEMO dataset**; the real shortlist is served solely to the signed-in admin. Only the admin can refresh data or change API keys/settings.
- **LLM research agent (optional, Groq free tier)** — annotates existing signals with a news-style `sentiment`, up to four whitelisted `risk_flags`, and a **bounded confidence adjustment** (±15) shown alongside the engine score, with a short rationale. See [LLM research agent](#llm-research-agent-groq-free-tier).
- **Collapsible sections & hamburger nav** — every major section can be expanded/collapsed, the header carries a hamburger menu at all screen sizes, and each signal page ends with a **"How confidence was derived"** breakdown showing the weighted sub-score math.
- **One-service deployment** — FastAPI serves both the API and the exported frontend, so the app runs on **Render + Neon with no Vercel and no Node server**.

---

## Access model

| Area | Visitor (no login) | Authorized user | Admin |
|---|---|---|---|
| Daily view, History, Macro, Charts | ✅ **synthetic DEMO data only** | ✅ live data | ✅ live data |
| Refresh data button | — | — | ✅ |
| Research agent button | — | — | ✅ |
| Settings / API keys | — | — | ✅ |
| Users (add / disable / promote) | — | — | ✅ |

**Anonymous visitors never see live signals.** Every public read endpoint checks for a valid
token: with one you get the real shortlist from the database, without one you get a cached
dataset built from the deterministic MOCK providers (see
`backend/app/services/demo_service.py`). Demo rows use ids from `900000` up, so they can never
collide with real rows, and an anonymous request for a real signal id returns 404 with a
"sign in to view live signals" message. A missing **or invalid** token is treated as anonymous —
a logged-out browser sees the demo, not a 401. The UI shows a **Demo** banner whenever the
payload is synthetic.

### Adding authorized users

The account created from `ADMIN_USERNAME` / `ADMIN_PASSWORD` is the **first administrator**.
Sign in as an admin and open **Users** to:

- **add a user** — username (3–64 chars, letters/digits/`.`/`_`/`-`) and a password of 8+ characters; tick *Administrator* to give them full privileges
- **disable / re-enable** an account (a disabled user's existing token stops working immediately)
- **promote / demote** between member and admin
- **reset a password**
- **delete** an account (its stored API credentials go with it)

Guards: usernames are unique (case-insensitive), you cannot delete your own account, and the
**last active administrator** can never be demoted, disabled or deleted — so an admin cannot
lock everyone out of the management screens. Non-admins get `403` from the admin-only endpoints
(`/api/users`, `/api/settings`, `/api/refresh`, `/api/backtest`, `/api/research`), and the
**Users** and **Settings** links only appear in the nav for admins.

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

---

## How confidence is derived

Confidence is a **blended rating**, not a single technical score. Two factor groups are each
scored 0–100, mixed by the setup's family, and then adjusted for context.

### Step 1 — the two factor groups

| Continuation factors | Measures |
|---|---|
| `trend_separation` | How far price sits beyond the 50 SMA, in ATRs |
| `ma_alignment` | Separation of the 20 and 50 SMA |
| `pullback_control` | How shallow and orderly the pullback was |
| `structure_clean` | No flush bar against the trend before the trigger |
| `trigger_strength` | EXE candle quality + how decisively and promptly it cleared the LP |
| `participation` | Volume versus its 20-day average |

| Reversal factors | Measures |
|---|---|
| `flush_intensity` | Size and aggression of the flush into the level |
| `liquidity_sweep` | Whether a prior swing extreme was taken out |
| `reversal_trigger` | Recovery candle quality + how far it reclaimed past the LP |
| `exhaustion` | RSI stretch and distance from the mean |
| `structure` | Pattern quality (double top/bottom similarity, retracement depth) |

### Step 2 — blend by setup family

`blend = continuation × w_cont + reversal × w_rev`, with per-setup weights in `FAMILY_WEIGHTS`:

| Family | Continuation weight | Reversal weight | Rationale |
|---|---|---|---|
| `UC1` `UC2` `DC1` `DC2` | 60% / 55% | 40% / 45% | The trend is the primary edge; the pullback merely times the entry |
| `UR1` `DR1` `UR2` `DR2` | 35% / 30% | 65% / 70% | The turn is the primary edge; the prior trend is only context |

### Step 3 — context adjustments

| Adjustment | Range | Source |
|---|---|---|
| Regime alignment | ±8 | Market regime versus the trade direction |
| Sector rotation | ±5 | Leading vs lagging sector |
| **Counter impact** | −15 … +5 | Macro events and media that argue **against** the recommendation |

`confidence = clamp(blend + regime + sector + counter_impact, 0, 100)`, labeled Low 0–40,
Medium 41–70, High 71–100.

### Counter impact (the "counter recommended" factor)

This term deliberately looks for what argues **against** the signal. It is computed at generation
time from the event backdrop and stored per signal (`confidence_components.counter_impact`, with
the reasons in `event_flags.counter_impact_drivers`):

- the **economic calendar's net sentiment**, signed against the trade direction (a weak calendar hurts a long and helps a short) — up to −10
- a **high-impact event within 2 days** — −5
- **rising yields** pressuring a rate-sensitive long — −3
- **earnings due within 7 days** (gap risk) — −2
- supportive backdrop — up to +5

The **media** half comes from the research agent: it returns a `counter_impact` magnitude (0–15)
for adverse macro/sector/news coverage against the recommended direction, and that figure is
shown alongside the macro one on the signal page. Its net effect already sits inside the
annotation's `confidence_delta` on `adjusted_confidence`.

> Both the macro term and the media magnitude are **penalties**: they can only subtract (plus a
> small supportive bonus for the macro term). Every anchor is a named constant at the top of
> `backend/app/core/sma_strategy.py` (`FAMILY_WEIGHTS`, `REGIME_ADJUSTMENT_MAX`,
> `SECTOR_ADJUSTMENT_MAX`, `COUNTER_IMPACT_MIN/MAX`), and each signal's full arithmetic is
> printed on its page under **How confidence was derived**.

**Also applied:** earnings within 7 days suppress the signal entirely unless confidence > 80 and
earnings plays are enabled; and a structural stop further than 15% from entry (`MAX_RISK_PCT`)
drops the setup as untradeable.

---

**Macro data** comes from **Yahoo Finance** (real SPY vs 200-day MA, VIX, 10-year yield, and sector-ETF relative strength) via `httpx` — no key required — with FRED/Finnhub (optional keys) and the built-in MOCK provider as fallbacks. Stock prices/signals continue to use **Alpaca**.

---

## LLM research agent (Groq free tier)

An optional agent that **annotates existing signals** — it never invents new ones:

| Field | What it is |
|---|---|
| `sentiment` | The model's near-term view of the **stock**: `bullish` / `bearish` / `neutral` / `mixed` |
| `risk_flags` | 0–4 concrete risks from a **fixed vocabulary** (`earnings_soon`, `extended_move`, `wide_stop`, `weak_volume`, `counter_trend`, `overbought`, `event_gap_risk`, …) |
| `confidence_delta` | **Bounded** adjustment (±15 by default) to how likely the setup is to work **in its stated direction** |
| `adjusted_confidence` | `engine confidence + delta`, clamped to 0–100 |
| `rationale` | ≤280 characters, tied to the numbers supplied |

Get a free key at **[console.groq.com/keys](https://console.groq.com/keys)**, then set `GROQ_API_KEY`
(or paste it under **Settings → Optional providers** — it's Fernet-encrypted at rest like the other keys).

**How it works**

1. The admin clicks **◆ Research signals** on the Daily View (or `POST /api/research/run`).
2. For each signal the backend builds a **compact brief** — setup, direction, entry/stop/target,
   R:R, engine confidence components, triggered rules, last 8 closes, RSI/ATR, distance from the
   20/50 SMA, 5-day and 20-day change, volume ratio, regime, VIX, earnings proximity, macro
   sentiment — and asks Groq for a JSON verdict.
3. The run happens in a **background thread** (Groq free-tier calls are sequential), and the UI
   polls `GET /api/research/status`. Results appear on the table, cards and the signal page.

**Free-tier notes.** Groq caps requests *and* tokens per minute, so prompts stay small, calls are
sequential with a configurable pause (`LLM_RESEARCH_PAUSE_SECONDS`), 429/5xx are retried with
backoff honouring `Retry-After`, and a run processes at most `LLM_RESEARCH_MAX_SIGNALS` (default 20).
Confirmed free-plan models include `openai/gpt-oss-120b` (default), `openai/gpt-oss-20b` and
`qwen/qwen3.8-27b`; set `GROQ_MODEL` to switch. If your key lacks access to a model, the error is
returned per-signal and surfaced in the status response — it never breaks signal generation.

**Safety.** Model output is treated as **untrusted data**: sentiment is whitelisted, flag names are
whitelisted and capped, the delta is clamped and NaN-guarded, and the rationale is length-capped and
stripped of newlines. The engine's own `confidence` is never overwritten — the adjusted value is
stored beside it in `Signal.annotation` so both stay auditable. The agent is **informational only
and is not financial advice**.

**Endpoints**

| Method | Path | Access |
|---|---|---|
| `GET` | `/api/research/status` | Public — configured? model, annotated/pending counts, last run |
| `POST` | `/api/research/run` | Admin — start a pass (`{limit?, signal_ids?, force?}`) |
| `POST` | `/api/research/test` | Admin — one tiny round-trip to verify the key |
| `DELETE` | `/api/research` | Admin — clear every annotation |

---

## Deploying on Render + Neon (no Vercel)

The frontend is a **static export** and FastAPI serves it at `/`, so the whole app is a
**single service**. `render.yaml` is a ready blueprint:

1. Push this repo to GitHub.
2. Create a free Postgres at **[neon.tech](https://neon.tech)** and copy the connection string,
   inserting `+psycopg2` after `postgresql`, e.g.
   `postgresql+psycopg2://user:pass@ep-xxx.aws.neon.tech/neondb?sslmode=require`
3. Render → **New → Blueprint** → pick the repo (it reads `render.yaml`), then fill in the
   prompted secrets: `DATABASE_URL`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ADMIN_PASSWORD`,
   and optionally `GROQ_API_KEY` for the research agent.
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

See `.env.example` for the full list. Key variables: `SECRET_KEY`, `DATABASE_URL`, `STATIC_DIR`, `DATA_PROVIDER`, `ALPACA_*`, `FINNHUB_API_KEY`, `FRED_API_KEY`, `POLYGON_API_KEY`, `GROQ_API_KEY`/`GROQ_MODEL`, `LLM_*` (research agent), `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `CORS_ORIGINS`, and the `CRON_*` schedules.

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
