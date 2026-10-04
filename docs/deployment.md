# Free cloud deployment

This guide deploys the app for free using:

| Piece | Service | Cost | Notes |
|---|---|---|---|
| **App** (FastAPI + the built Next.js UI) | **Render** | Free web service | **One service, one URL.** Spins down after 15 min idle; wakes on request (~30–60 s cold start) |
| Database | **Neon** (or Supabase) | Free Postgres | No expiry, generous limits |
| Daily 8:30 PM SGT pull | **GitHub Actions** | Free | Runs the cron reliably even when the backend is asleep |

> **No Vercel needed.** The frontend is built to a **static export** and FastAPI serves it
> at `/`, so the UI and the API share one origin — no CORS, no second host, no Node server
> in production. (`render.yaml` in the repo is a ready-made blueprint for exactly this.)

> **Why GitHub Actions for the schedule?** Render's free tier puts the service to
> sleep when idle, so the in-process scheduler won't fire. GitHub Actions runs on
> its own schedule and writes directly to the shared Postgres database.

## 0. Prerequisites

- A **GitHub** account, and **git** installed locally.
- A **Render** and **Neon** account (both free tiers, no card needed).
- Your **Alpaca** keys.

Push the project to GitHub first:

```bash
cd "C:\Users\Spare Parts\Swing Trading Picks"
git init
git add .
git commit -m "Initial commit"
# create an empty repo on github.com, then:
git remote add origin https://github.com/<you>/swing-trading-picks.git
git branch -M main
git push -u origin main
```

## 1. Neon — create the free Postgres database

1. Sign in at [neon.tech](https://neon.tech) → **Create project**.
2. Copy the **connection string**. It looks like:
   `postgresql://user:pass@ep-xxx.aws.neon.tech/neondb?sslmode=require`
3. Convert it for SQLAlchemy by inserting `+psycopg2`:
   `postgresql+psycopg2://user:pass@ep-xxx.aws.neon.tech/neondb?sslmode=require`

Keep this string — you'll set it as `DATABASE_URL` in two places (Render and GitHub).

## 2. Render — deploy the whole app (one service)

**Option A — blueprint (fastest):** Render → **New → Blueprint** → pick the repo. Render reads
`render.yaml` and prompts for the secret values (`DATABASE_URL`, `ALPACA_API_KEY`,
`ALPACA_SECRET_KEY`, `ADMIN_PASSWORD`). Approve and it builds.

**Option B — manual web service:**

1. Sign in at [render.com](https://render.com) → **New → Web Service**.
2. Connect your GitHub repo.
3. Settings:
   - **Root Directory**: *(leave as the repo root — the Dockerfile is at the top level)*
   - **Runtime**: `Docker`
   - **Dockerfile Path**: `./Dockerfile`
   - **Instance Type**: `Free`
   - **Health Check Path**: `/api/health`
4. Environment variables:

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | your Neon `postgresql+psycopg2://...` string |
   | `SECRET_KEY` | a long random string (e.g. from a password generator) |
   | `STATIC_DIR` | `/app/static` |
   | `DATA_PROVIDER` | `alpaca` (or `auto`) |
   | `DISABLE_SCHEDULER` | `true` |
   | `ALPACA_API_KEY` | your Alpaca key *(or enter it later in the app's Settings UI)* |
   | `ALPACA_SECRET_KEY` | your Alpaca secret |
   | `ALPACA_PAPER` | `true` |
   | `ADMIN_USERNAME` | `admin` |
   | `ADMIN_PASSWORD` | a strong password |
   | `GROQ_API_KEY` | *(optional)* free key from [console.groq.com/keys](https://console.groq.com/keys) — enables the LLM research agent |

   > `CORS_ORIGINS` is **not** needed: the UI and API are same-origin.

5. Click **Deploy**. The first build compiles the frontend and installs Python deps (a few minutes).
6. Once deployed, `https://<your-service>.onrender.com` **is the whole app** — open it and sign
   in with your `ADMIN_USERNAME` / `ADMIN_PASSWORD`. (`/api/health` for health, `/docs` for the API.)

> **Note:** you can skip the `ALPACA_*` env vars and instead enter the keys in the
> app's **Settings → Alpaca** after deploying. The GitHub Actions cron needs the
> keys as secrets (below) either way.

## 3. GitHub Actions — the daily 8:30 PM SGT pull

The workflow is already in the repo at `.github/workflows/daily-cron.yml` (scheduled
`30 12 * * *` UTC = 8:30 PM Singapore time). Add these **repository secrets**
(Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `DATABASE_URL` | your Neon connection string |
| `SECRET_KEY` | the **same** secret you set on Render |
| `ALPACA_API_KEY` | your Alpaca key |
| `ALPACA_SECRET_KEY` | your Alpaca secret |
| `DATA_PROVIDER` | `auto` (optional) |

Then run it once manually (**Actions → Daily signal generation → Run workflow**) to
verify, and confirm signals appear in the app.

## 4. Change the default admin password

Set these on **Render** and restart:

| Key | Value |
|---|---|
| `ADMIN_USERNAME` | your username |
| `ADMIN_PASSWORD` | a strong password |

## Caveats & tips

- **Cold start:** Render free sleeps after ~15 min idle; the first request wakes it
  (30–60 s). Use a free uptime pinger (e.g. UptimeRobot) hitting `/api/health` if you
  want it warm — but it will still sleep per Render's policy.
- **Both schedulers:** set `DISABLE_SCHEDULER=true` on Render so it doesn't fight
  GitHub Actions; GitHub Actions is the reliable scheduler.
- **No options leg:** the app reads stock prices only, so bearish setups are quoted on
  the underlying itself — no options subscription is needed.
- **Index futures (MES):** pulled from Yahoo's public chart API (no key). If Yahoo is
  blocked from your host the futures are simply omitted; equities are unaffected. Set
  `INDEX_FUTURES_ENABLED=false` to switch them off.
- **Updating the UI:** any change under `frontend/` requires a Render rebuild (the UI is
  compiled into the image). Render auto-deploys on push, so just `git push`.
- **Public repo warning:** if your repo is public, never commit `.env` or real
  secrets. Keys entered via the app's Settings UI are stored encrypted in the DB.

## Local production check

```bash
docker compose up --build
# whole app (UI + API) on one port:
# http://localhost:8000
```
