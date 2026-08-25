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

**Status:** Idea only, no implementation
**Effort:** 1-2 hours
**Impact:** Makes all your projects discoverable from one place

### The problem
Three repos exist (`media-stack` private, `Stackalicious` public mirror deleted, `StackScripts` public redistribution deleted) plus Metacacharr. Nothing answers "what has this person built" in one place.

### Constraint
`media-stack` is private by design and must stay that way.

### Options considered
1. **GitHub Profile README** — public, shows pinned repos, no code exposure
2. **GitHub Topics/Descriptions** — lightweight, no new repo needed
3. **Static site** — overkill for this scale

### Recommendation
Option 1 (Profile README) + Option 2 (consistent topics/descriptions). Zero maintenance, maximum discoverability.

---

## 4. PLANS.md Phase 8: Naming Cleanup — DEFERRED

**Status:** Phase 8a and 8b completed (2026-08-13). Phase 8 (whole-stack naming cleanup) was the original plan but the actual work was narrower — only 12 functions renamed, not the full 150+ originally scoped.

### What remains
The original Phase 8 scope included renaming ~150 fish functions with drifting verb order. The actual cleanup renamed 12 and added a linter. If you want the broader rename (e.g., standardizing all `stack-plex-*` to a consistent verb pattern), that's new work.

### Effort
2-3 hours for the full rename pass

---

## 5. Open Items from docs/stack-audit-2026-08-23.md

**Status:** Audit complete, some items flagged but not fixed

### Items flagged, not fixed
1. **AuditLog is write-only** — `services/auth/router.py` writes login/logout rows but nothing reads them. Either build a reader or stop writing.
2. **`main.py:40-41` silent `except Exception: pass`** — gateway lookup fails silently. Low priority, fallback is intentional.
3. **`services/host/router.py` automation-exception comments** — borderline convention compliance. Minor.
4. **`DEDUP_SUFFIX_RE` ambiguity** — matches both `(2)` dedup suffix and `(2020)` year. Potential false positive on year-suffixed filenames.

### Effort
1-2 hours total for all four

---

## Review Checklist

Before executing any of the above, confirm:

- [ ] **Upstream monitoring** — Do you want weekly release checks? (Y/N)
- [ ] **Discord alerts** — Do you use Discord or is ntfy enough? (Y/N/Skip)
- [ ] **Hub repo** — Want a GitHub profile README? (Y/N)
- [ ] **Fish function rename** — Broad rename beyond the 12 already done? (Y/N)
- [ ] **AuditLog reader** — Build it or stop writing? (Build/Stop/Skip)
- [ ] **Audit fixes** — Fix the 4 flagged items? (Y/N)