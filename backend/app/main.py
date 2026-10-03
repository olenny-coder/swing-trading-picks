"""FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload

The app is a plain ASGI app, so it deploys anywhere. When a static frontend
build is present (``STATIC_DIR``, default ``static/``) it is served from the same
origin as the API, which makes the whole product a single service — this is how
the Render + Neon deployment runs without Vercel.
"""
from __future__ import annotations

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
    users,
)
from .api.auth import bootstrap_admin
from .config import get_settings
from .database import SessionLocal, init_db
from .seed import seed_if_empty
from .tasks.scheduler import start_scheduler, stop_scheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        bootstrap_admin(db)
    finally:
        db.close()
    # Demo bootstrap (no-op when signals already exist / real keys configured).
    seed_if_empty()
    if not settings.disable_scheduler:
        start_scheduler()
    yield
    if not settings.disable_scheduler:
        stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Swing trading setups (UC1, UC2, DC1, DC2, UR1, DR1, UR2, DR2) "
    "from the SMA 20/50 flow system for liquid US equities, with macro/earnings "
    "filtering and API-key management.",
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
