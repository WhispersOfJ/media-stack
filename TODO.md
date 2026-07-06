# TODO

Planned work not yet started. Once a line item ships, it moves to [CHANGELOG.md](CHANGELOG.md)
and gets removed from here.

## Add Jellyfin + companion apps

- [ ] **Jellyfin** — media server, alongside the existing native Plex install
- [ ] **Jellyseerr** — request management for Jellyfin (Seerr/Overseerr equivalent; confirm
      whether the stack's existing `seerr` image already supports a Jellyfin backend before
      adding a second requests container)
- [ ] **Jellystat** — watch statistics/history for Jellyfin (Tautulli equivalent), needs its
      own Postgres database like Zilean
- [ ] **jfa-go** — user invite/account management for Jellyfin
- [ ] Point Bazarr at Jellyfin too (it already supports multiple media servers — config
      change, not a new container)
- [ ] Decide on GPU passthrough / hardware transcoding devices for Jellyfin
- [ ] Add all new services to Heimdall once live (new "Media Server" / "Monitoring & Tools"
      tiles, following the pattern from [2.3.0])
- [ ] Add Recyclarr/quality-profile equivalents if Jellyfin needs its own custom formats
