# Free cloud deployment

This guide deploys the app for free using:

| Piece | Service | Cost | Notes |
|---|---|---|---|
| Frontend (Next.js) | **Vercel** | Free | Auto-deploys from GitHub |
| Backend (FastAPI) | **Render** | Free web service | Spins down after 15 min idle; wakes on request (~30–60 s cold start) |
| Database | **Neon** (or Supabase) | Free Postgres | No expiry, generous limits |
| Daily 8:30 PM SGT pull | **GitHub Actions** | Free | Runs the cron reliably even when the backend is asleep |

> **Why GitHub Actions for the schedule?** Render's free tier puts the backend to
> sleep when idle, so the in-process scheduler won't fire. GitHub Actions runs on
> its own schedule and writes directly to the shared Postgres database.

## 0. Prerequisites

- A **GitHub** account, and **git** installed locally.
- A **Vercel**, **Render**, and **Neon** account (all have free tiers, no card needed).
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

## 2. Render — deploy the backend

1. Sign in at [render.com](https://render.com) → **New → Web Service**.
2. Connect your GitHub repo.
3. Settings:
   - **Root Directory**: `backend`
   - **Runtime**: `Docker` (Render auto-detects `backend/Dockerfile`)
   - **Instance Type**: `Free`
4. Environment variables:

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | your Neon `postgresql+psycopg2://...` string |
   | `SECRET_KEY` | a long random string (e.g. from a password generator) |
   | `DATA_PROVIDER` | `auto` |
   | `DISABLE_SCHEDULER` | `true` |
   | `ALPACA_API_KEY` | your Alpaca key *(or enter it later in the app's Settings UI)* |
   | `ALPACA_SECRET_KEY` | your Alpaca secret |
   | `ALPACA_PAPER` | `true` |
   | `CORS_ORIGINS` | `https://<your-app>.vercel.app` |

5. Click **Deploy**. The first build takes a few minutes.
6. Once deployed, note the URL (e.g. `https://swing-api.onrender.com`). Test it at
   `https://swing-api.onrender.com/api/health`.

> **Note:** you can skip the `ALPACA_*` env vars and instead enter the keys in the
> app's **Settings → Alpaca** after deploying. The GitHub Actions cron needs the
> keys as secrets (below) either way.

## 3. Vercel — deploy the frontend

1. Sign in at [vercel.com](https://vercel.com) → **Add New → Project** → import the repo.
2. Configure:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Next.js (auto-detected)
3. Environment variable:

   | Key | Value |
   |---|---|
   | `API_URL` | `https://swing-api.onrender.com` (your Render backend URL) |

4. **Deploy**. Vercel gives you `https://<your-app>.vercel.app`.
5. Open it and sign in with `admin` / `changeme` (change these via env vars — see below).

## 4. GitHub Actions — the daily 8:30 PM SGT pull

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

## 5. Change the default admin password

Set these on **Render** (backend) and restart:

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
- **Options data:** put-option *contract* recommendations need an Alpaca options
  subscription or a Polygon.io key; without them, bearish setups still appear with
  underlying levels.
- **Public repo warning:** if your repo is public, never commit `.env` or real
  secrets. Keys entered via the app's Settings UI are stored encrypted in the DB.
