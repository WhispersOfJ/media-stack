FROM python:3.12.7-slim-bookworm

WORKDIR /app

# Unbuffered stdout - print()'s default block-buffering inside a non-tty
# container would otherwise sit in memory and not reach `docker logs -f`
# in time for live per-item progress lines to actually stream.
ENV PYTHONUNBUFFERED=1

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
