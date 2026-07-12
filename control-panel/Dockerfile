FROM python:3.12.7-slim-bookworm

WORKDIR /app

# restic - for /api/backup-verify and /api/backup-restore-test, reading the
# same two repos scripts/backup-config.sh writes to (mounted read-only below).
RUN apt-get update && apt-get install -y --no-install-recommends restic \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static ./static

EXPOSE 8420

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8420"]
