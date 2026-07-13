---
name: trash-guides-applier
description: Apply TRaSH-Guides recommended quality profiles and custom formats to Radarr and Sonarr via their REST APIs, using the JSON profile definitions in profiles/. Use when the user asks to set up or refresh quality profiles following TRaSH-Guides, add a custom format (e.g. HDR10+, remux-tier scoring), or wants to know what recyclarr (already deployed in this stack) is/isn't covering. Trigger phrases: "apply trash guides profiles", "set up quality profiles", "add this custom format", "what does recyclarr sync", "refresh radarr/sonarr profiles".
---

# TRaSH-Guides Applier

This stack already runs `recyclarr` (config at `config/recyclarr/recyclarr.yml`) for
ongoing, scheduled TRaSH-Guides sync — **prefer editing `recyclarr.yml` and letting
recyclarr run for routine profile updates**, since that's the stack's existing source of
truth and it runs on a schedule already configured in the container.

This skill exists for the cases recyclarr doesn't cleanly cover in one pass:

- **Bootstrapping a brand-new Radarr/Sonarr instance** before recyclarr has ever run,
  from a known-good local snapshot (`profiles/*.json`) rather than depending on a live
  fetch from the TRaSH-Guides GitHub repo.
- **One-off custom format additions** the user wants applied immediately, not on
  recyclarr's next scheduled run.
- **Inspecting/diffing** what's currently applied against the local profile snapshot,
  to answer "is recyclarr actually keeping up."

## Profile files

- `profiles/radarr-profiles.json` — quality profiles + custom formats for Radarr,
  following TRaSH-Guides' movie recommendations (WEB-DL/Remux tiering, HDR bonus scoring).
- `profiles/sonarr-profiles.json` — same shape for Sonarr (episode quality tiering).

Each file has the shape:
```json
{
  "quality_profiles": [
    {"name": "HD Bluray + WEB", "upgrade_allowed": true, "cutoff": "WEB 1080p", "items": [...]}
  ],
  "custom_formats": [
    {"name": "HDR10+", "score": 30, "specifications": [...]}
  ]
}
```

## Usage

```bash
python3 applier.py apply radarr --profiles profiles/radarr-profiles.json
python3 applier.py apply sonarr --profiles profiles/sonarr-profiles.json
python3 applier.py diff radarr --profiles profiles/radarr-profiles.json   # what would change
python3 applier.py list-current radarr                                    # what's live right now
```

Auth via the same `RADARR_URL`/`RADARR_API_KEY` (and Sonarr equivalent) environment
variables as `arr-config-sync` — no separate credential config.

## Safety rules

- `apply` is additive/updating only by matching custom-format and quality-profile `name`:
  it creates missing ones and updates changed ones, but never deletes a profile/format
  that exists live but isn't in the local JSON — a user may have a profile that's
  intentionally not TRaSH-standard.
- Always run `diff` before `apply` when the profile JSON files have been hand-edited,
  to catch typos before they hit a live Radarr/Sonarr instance.
- If recyclarr is running and actively managing profiles, applying conflicting changes
  here will just get overwritten on recyclarr's next run — check
  `config/recyclarr/recyclarr.yml` first if results seem to "revert" unexpectedly.
