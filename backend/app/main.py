"""FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload

The app is a plain ASGI app, so it deploys anywhere. When a static frontend
build is present (``STATIC_DIR``, default ``static/``) it is served from the same
origin as the API, which makes the whole product a single service — this is how
the Render + Neon deployment runs without Vercel.
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import (
    auth,
    backtest,
    macro,
    refresh,
    research,
    settings as settings_router,
    signals,
    smc,
    users,
)
from .api.auth import bootstrap_admin
from .config import get_settings
from .database import SessionLocal, init_db
from .seed import seed_if_empty
from .services import demo_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")

settings = get_settings()


def _seed_in_background() -> None:
    """Seed the MOCK demo dataset without blocking startup.

    uvicorn binds its port only *after* this lifespan function returns, so a slow
    startup is indistinguishable from a crash: both surface as Render's
    "No open ports detected". Seeding is optional, so it runs on a background
    thread and a failure is logged rather than fatal — a seeding problem must
    never stop the service from serving.
    """
    try:
        result = seed_if_empty()
        logger.info("demo seed finished: %s", result)
    except Exception:
        logger.exception("demo seeding failed; the app keeps serving")


def _warm_demo_cache() -> None:
    """Build the synthetic DEMO dataset ahead of the first visitor.

    The dataset and the SMC scan over it are pure CPU work over generated series
    (expensive on a free instance), and they would otherwise be built inside the
    first anonymous request. Warming them here keeps that request fast.
    """
    try:
        demo_service.dataset()
        demo_service.smc_scan_payload()
        logger.info("demo dataset ready")
    except Exception:
        logger.exception("demo dataset warm-up failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Required, and fast: the schema and the bootstrap account.
    init_db()
    db = SessionLocal()
    try:
        bootstrap_admin(db)
    finally:
        db.close()

    # No scheduled downloads: the admin pulls fresh data on demand with the
    # Refresh button. Nothing here reaches out to a provider on a timer.

    mode = (settings.seed_mode or "background").strip().lower()
    if mode == "sync":
        # Tests and local demos want the seeded data present before the first
        # request. The demo cache is still warmed off-thread: it is only a
        # latency optimisation, and warming it here would slow every test run.
        _seed_in_background()
    elif mode != "off":
        threading.Thread(target=_seed_in_background, name="demo-seed", daemon=True).start()

    threading.Thread(target=_warm_demo_cache, name="demo-warm", daemon=True).start()

    yield


app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description=(
        "Smart Money Concepts multi-timeframe analysis: daily market structure, break of "
        "structure and the fair value gap behind it, refined on the 4-hour chart for the "
        "entry, stop and target. Data is refreshed by the administrator on demand."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(settings_router.router, prefix=API_PREFIX)
app.include_router(signals.router, prefix=API_PREFIX)
app.include_router(smc.router, prefix=API_PREFIX)
app.include_router(macro.router, prefix=API_PREFIX)
app.include_router(backtest.router, prefix=API_PREFIX)
app.include_router(refresh.router, prefix=API_PREFIX)
app.include_router(research.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


def _frontend_dir() -> Path | None:
    """Locate a built frontend, if one is present next to the backend."""
    candidates = [
        Path(settings.static_dir),
        Path(__file__).resolve().parent.parent / settings.static_dir,
        Path(__file__).resolve().parent.parent.parent / "frontend" / "out",
        Path.cwd() / "static",
    ]
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate
    return None


_frontend = _frontend_dir()

if _frontend is not None:
    # Serve the exported site at the root. Mounted last so /api/* and /docs win.
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
else:

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        """Fallback when no frontend build is bundled (API-only deployment)."""
        return {
            "app": settings.app_name,
            "docs": "/docs",
            "health": "/api/health",
            "hint": "Build the frontend (cd frontend && npm run build) to serve the UI here.",
        }
