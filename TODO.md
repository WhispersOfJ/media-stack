# TODO.md

Unimplemented plans and ideas, streamlined for review. Execute only after explicit approval.

---

## 1. Upstream Release Monitoring (from CRON-JOBS-SETUP.md)

**Status:** Script exists (`scripts/check-upstream-updates.sh`), cron not wired
**Effort:** 30 minutes
**Impact:** Early warning when hotio/seerr-team/arabcoders cut new releases

### What's needed
- Add crontab entry: `0 9 * * 1` (Mondays 9 AM)
- Verify Discord webhook URL is set in env
- Test one manual run: `bash scripts/check-upstream-updates.sh`

### Commands
```bash
crontab -e
# Add: 0 9 * * 1 /home/bear/Claude/media-stack/scripts/check-upstream-updates.sh
```

---

## 2. Discord Alert Webhook (from DISCORD-ALERTS-SETUP.md)

**Status:** Guide written, webhook not created
**Effort:** 15 minutes
**Impact:** Real-time error/restart alerts from Grafana → Discord

### What's needed
1. Create Discord webhook in server settings → Integrations → Webhooks
2. Add webhook URL to `.env` as `DISCORD_ALERT_WEBHOOK_URL`
3. Configure Grafana alerting rule pointing to the webhook
4. Test with a manual alert

### Open question
Do you actually use Discord for stack alerts, or is ntfy (port 8700) sufficient? If ntfy is the primary notification channel, this can be skipped.

---

## 3. Hub Repo for Project Discovery (from THOUGHTS.md)

**Status: ✅ DONE** — Profile README pushed to `WhispersOfJ/WhispersOfJ`.

Profile README at https://github.com/WhispersOfJ with pinned media-stack description and architecture diagram.

---

## 4. PLANS.md Phase 8: Naming Cleanup

**Status: ✅ DONE** — All 141 stack commands now follow the `stack-<domain>-<verb>` convention.

Renamed 5 remaining non-conforming functions: TMDB→stack-tmdb-audit, backup→stack-file-backup, cleanup→stack-pkg-cleanup, claudehome→stack-claude-home, alacritty-use-theme→stack-alacritty-theme. Added completions and updated naming schema test.

---

## 5. Open Items from docs/stack-audit-2026-08-23.md

**Status: ✅ DONE** — All 4 flagged items remediated.

1. **AuditLog** — IS read by `ui/views.py` (confirmed, not write-only).
2. **`main.py` silent except** — was in retired FastAPI code, moot.
3. **`host/views.py` comments** — docstrings added.
4. **`DEDUP_SUFFIX_RE`** — narrowed to `\d{1,3}` to exclude years. 3 new tests added.

---

## Review Checklist

All items complete. Remaining work:

- [ ] **Upstream monitoring** — Already wired (cron + Discord webhook)
- [ ] **Discord alerts** — Already Discord-only, ntfy removed