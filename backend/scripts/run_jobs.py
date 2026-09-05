"""Run the daily ingestion + signal-generation jobs once (used by CI/cron).

    python scripts/run_jobs.py

Set DATABASE_URL and provider keys via environment variables. This is the
entrypoint used by the GitHub Actions daily-cron workflow and any external
scheduler that cannot rely on the in-process APScheduler.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db  # noqa: E402
from app.tasks.scheduler import generate_signals_job, ingest_daily_job, ingest_macro_job  # noqa: E402


def main() -> None:
    init_db()
    print("ingest_daily_job:", ingest_daily_job())
    ingest_macro_job()
    print("generate_signals_job:", generate_signals_job())
    print("done")


if __name__ == "__main__":
    main()
