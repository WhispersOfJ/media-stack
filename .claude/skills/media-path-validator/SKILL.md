---
name: media-path-validator
description: Validate that media library and download paths are correctly mounted, writable, and on the same filesystem for hardlinks (not copies) between the Arr apps' download and library folders. Use when the user reports an Arr app "importing" via slow copy instead of instant hardlink/move, sees permission errors on import, sets up a new root folder or download client path, or after any docker-compose volume/mount change. Trigger phrases: "radarr is copying instead of hardlinking", "check the media paths", "permission denied importing", "validate mount points", "did I break the paths".
---

# Media Path Validator

Cross-Arr-app hardlinking (instant "import" instead of a slow copy across filesystems)
requires the download client's completed-download folder and the library's root folder
to be **on the same filesystem inside the container** — not just both "mounted", but
sharing the same device ID. This is the single most common Arr-stack misconfiguration,
and it's invisible until an import happens (Radarr/Sonarr silently fall back to copy+delete,
which works but is slow and doubles disk I/O during import).

## What it checks

1. **Existence** — does the path exist inside the container/host as configured?
2. **Writability** — can the media-stack's runtime user actually write there?
3. **Same-filesystem** — do a download path and a library path share `st_dev` (i.e. would
   `os.link()` succeed), using Python's `os.stat()`.
4. **Case/trailing-slash consistency** — catches the classic `/media/movies` vs
   `/media/movies/` root-folder mismatch that makes Radarr treat an existing folder as new.

## Usage

```bash
python3 validator.py check /downloads/complete /media/movies      # pairwise hardlink check
python3 validator.py check-all --config paths.json                # check every pair from a config file
python3 validator.py writable /media/tv
python3 validator.py exists /downloads/complete /media/movies /media/shows
```

`paths.json` format:
```json
{
  "pairs": [
    {"download": "/downloads/complete", "library": "/media/movies", "label": "radarr"},
    {"download": "/downloads/complete", "library": "/media/tv", "label": "sonarr"}
  ]
}
```

## Interpreting results

- `same_filesystem: false` between a download path and its matching library path is the
  root cause of "importing" behaving like a slow copy — fix by ensuring both paths are
  bind-mounted from the same host volume/root inside the container (this is a
  `docker-compose.yml` volume mapping issue, not something this skill can fix — it only
  diagnoses it).
- Report findings plainly; do not attempt to edit `docker-compose.yml` volume mappings
  automatically — that's a structural change the user should review, since it affects
  every container sharing the volume.

## Safety rules

- Read-only tool: it never creates, deletes, or moves files — only `os.stat`/`os.access`
  checks and a non-persisted `os.link()` dry-probe (creates a temp hardlink then removes
  it immediately, only when both paths already passed the existence/writability checks).
