FROM python:3.13-slim-bookworm

WORKDIR /app

# Unbuffered stdout
ENV PYTHONUNBUFFERED=1

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY manage.py .
COPY healthcheck.py .
COPY config ./config
COPY core ./core
COPY auth_app ./auth_app
COPY arr ./arr
COPY radarr ./radarr
COPY sonarr ./sonarr
COPY prowlarr ./prowlarr
COPY cleanuparr ./cleanuparr
COPY nzbdav ./nzbdav
COPY host ./host
COPY host_actions ./host_actions
COPY catalog ./catalog
COPY watchstate ./watchstate
COPY mdblist ./mdblist
COPY letterboxd ./letterboxd
COPY plex ./plex
COPY queue_app ./queue_app
COPY posters ./posters
COPY ratings ./ratings
COPY seerr ./seerr
COPY ui ./ui

# Collect static files for whitenoise to serve in production
ARG CONTROL_PANEL_SECRET_KEY=build-time-only
ENV CONTROL_PANEL_SECRET_KEY=${CONTROL_PANEL_SECRET_KEY}
RUN python manage.py collectstatic --noinput

EXPOSE 8420

CMD ["python", "manage.py", "runserver", "0.0.0.0:8420"]
