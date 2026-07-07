# Installer image, not a runtime image - the Stack itself is 22 separate
# upstream containers orchestrated by docker-compose.yml, not something this
# Dockerfile builds. This just bundles the repo's own tracked-and-portable
# files (compose file, Caddy config, scripts, systemd units, docs) so they
# can be dropped onto a new host with one `docker run` instead of a git
# clone. Rebuilt and republished to GHCR automatically on every push that
# touches these files - see .github/workflows/publish-installer.yml.
#
# Usage:
#   docker run --rm -v "$(pwd)":/out ghcr.io/whispersofj/media-stack:latest
FROM alpine:3.24

LABEL org.opencontainers.image.source="https://github.com/WhispersOfJ/media-stack"
LABEL org.opencontainers.image.description="Installer/updater for the media-stack repo's tracked files (compose file, Caddy config, scripts, systemd units, docs). Never contains .env, config/, media/, or usenet/ - those stay host-only."

WORKDIR /stack
COPY docker-compose.yml .env.example README.md CHANGELOG.md TODO.md ./
COPY caddy/ ./caddy/
COPY scripts/ ./scripts/
COPY systemd/ ./systemd/

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh ./scripts/*.sh

ENTRYPOINT ["/entrypoint.sh"]
