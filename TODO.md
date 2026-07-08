# TODO

Planned work not yet started. Once a line item ships, it moves to [CHANGELOG.md](CHANGELOG.md)
and gets removed from here.

- **Activate Discord alerting** — `scripts/notify-discord.sh`, the backup script, and the
  container-health watcher are all built and tested (currently no-op safe), and Watchtower's
  Shoutrrr notification env vars are commented out in `docker-compose.yml`. All three need a
  real webhook: set `DISCORD_WEBHOOK_URL` and `DISCORD_WATCHTOWER_SHOUTRRR_URL` in `.env`,
  then uncomment the three `WATCHTOWER_NOTIFICATION*` lines in the `watchtower` service and
  `docker compose up -d watchtower`.
