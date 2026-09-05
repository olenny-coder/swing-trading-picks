FROM python:3.11-slim

WORKDIR /app

# Install system deps needed for psycopg2/bcrypt wheels if any.
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Bind to Render's $PORT when set (defaults to 8000 for local Docker Compose).
CMD uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
