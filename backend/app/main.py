"""FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload
The app is a plain ASGI app (no reliance on the DSH shell), so it deploys to
Railway/Render/Fly.io or a VPS unchanged.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth, backtest, macro, refresh, settings as settings_router, signals
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
    description="Swing trading signals (BUY_STANDARD, BUY_DOJI_REVERSAL, SELL) "
    "for liquid US equities, with macro/earnings filtering and API-key management.",
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


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"app": settings.app_name, "docs": "/docs", "health": "/api/health"}
