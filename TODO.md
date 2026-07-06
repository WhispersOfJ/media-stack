# TODO

Planned work not yet started. Once a line item ships, it moves to [CHANGELOG.md](CHANGELOG.md)
and gets removed from here.

## Follow-ups from Jellyfin work ([2.4.0])

- [ ] Fix Bazarr's Plex connection (`ip: 127.0.0.1`, same bug the Radarr/Sonarr connections
      had) — needs a Plex API token, which wasn't on hand this session
- [ ] Full end-to-end verification (search → grab → import → play) once Decypharr and Zurg
      are back up — both were intentionally stopped for this session's work
- [ ] Bring Zurg back up, then add `/mnt/zurg/*` and `/mnt/decypharr/*` as additional Jellyfin
      library locations alongside the `/data/<type>` ones already added
