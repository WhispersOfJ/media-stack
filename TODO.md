# TODO

Planned work not yet started. Once a line item ships, it moves to [CHANGELOG.md](CHANGELOG.md)
and gets removed from here.

- **Investigate the Radarr/Sonarr mass library-loss event** found in
  [CHANGELOG.md v4.13.0](CHANGELOG.md): Radarr's log shows 1,605 movies deleted in a single
  0.1-second burst with no matching API call logged; Sonarr shows ~90 series added then removed
  with no deletion log line at all. Both apps now track zero items. Not caused by anything run
  in that session (only read-only `GET` requests preceded it). Check whether either app has a
  recent `Backup` task output worth restoring from (`System → Backup` in each app's UI, or
  `config/<app>/Backups/` on disk) before more content gets treated as "orphaned" and cleaned up
  on the assumption that a 0-item library is accurate.

- **`rclone-alldebrid` doesn't reliably survive `docker restart`**: found live while testing the
  Restart-All mount-ordering fix (see README's "Radarr-specific mount fragility" note for the
  sibling Zurg/Radarr bug this resembles). A plain `docker restart rclone-alldebrid` can leave
  its own `/mnt/all` FUSE mount in a `Transport endpoint is not connected` / `Socket not
  connected` state that the container's own restart-policy retries never clear on their own
  (observed retrying with growing backoff for 4+ minutes) - recovery needed a lazy unmount from
  outside the container's mount namespace (`docker run --rm --privileged -v /mnt:/mnt:rshared
  alpine umount -l /mnt/all`) followed by a fresh `docker restart rclone-alldebrid`. Same failure
  class as the Radarr one, just on a different container and without a known one-line fix yet -
  would also bite a Watchtower-triggered restart, not just Restart-All. Worth root-causing
  properly (an `unless-stopped` restart loop that can't self-heal is worse than Radarr's, which
  at least recovers cleanly with one manual restart).
