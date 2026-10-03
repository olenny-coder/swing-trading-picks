# ---------------------------------------------------------------------------
# Stage 1 — build the static frontend (Next.js export -> ./out)
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend

WORKDIR /fe

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./
# Same-origin API calls, so no NEXT_PUBLIC_API_BASE is needed.
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2 — FastAPI backend, serving the API *and* the exported frontend
# ---------------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# psycopg2 / bcrypt build deps (harmless when wheels are available).
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/scripts ./scripts

# The exported site; app.main serves STATIC_DIR at "/".
COPY --from=frontend /fe/out ./static

ENV PYTHONUNBUFFERED=1
ENV STATIC_DIR=/app/static
EXPOSE 8000

# Bind to Render's $PORT when set (defaults to 8000 for local Docker Compose).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
