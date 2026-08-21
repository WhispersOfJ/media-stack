# Builder stage: Install dependencies
FROM python:3.13-slim-bookworm as builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt


# Final stage: Distroless runtime
FROM gcr.io/distroless/python3:nonroot

WORKDIR /app

# Unbuffered stdout - print()'s default block-buffering inside a non-tty
# container would otherwise sit in memory and not reach `docker logs -f`
# in time for live per-item progress lines to actually stream.
ENV PYTHONUNBUFFERED=1

# Copy installed Python packages from builder
COPY --from=builder --chown=nonroot:nonroot /root/.local /home/nonroot/.local

# Set PATH to include user site-packages (where pip --user installs)
ENV PATH=/home/nonroot/.local/bin:$PATH
ENV PYTHONPATH=/home/nonroot/.local/lib/python3.13/site-packages:$PYTHONPATH

# Note: Distroless base (nonroot) removes util-linux, bash, apt, coreutils.
# Mount namespace features (nsenter) are unavailable.
# Plex health feature (/api/plex/scan-health) degrades gracefully (clear error).
# All Python features intact (pure code, API integrations, database migrations).

COPY settings_store.py main.py alembic.ini healthcheck.py .
COPY static ./static
COPY core ./core
COPY models ./models
COPY services ./services
COPY migrations ./migrations

EXPOSE 8420

# Distroless uses nonroot user (uid: 65532) by default
USER nonroot

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8420"]
