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
