# AGENTS.md

Guidance for AI coding agents working in this repo. Read `CLAUDE.md` first for architecture
orientation, common commands, and facts that span multiple files. This file covers the sync
obligation to this repo's one remaining downstream sibling.

## Downstream sibling

- **`../StackMaster`**: the standalone, redistributable CLI + control panel + docs, generalized
  (installer-driven credentials, no hardcoded IP/paths) for use without cloning this repo.
  `docker-compose.full-stack.yml` there mirrors this repo's `docker-compose.yml` service-for-
  service; `control-panel/app.py` there mirrors this repo's `control-panel/app.py`.

**Correction (2026-07-19): `Stackalicious` and `StackScripts` (formerly two separate downstream
siblings) were deleted outright from GitHub at the user's explicit request**, after being
subtree-imported into `StackMaster` with full history preserved and a completeness check
confirming every file in both final trees mapped to something in `StackMaster`. `StackMaster`
is now the only downstream sibling - do not recreate the old two-repo split, and don't trust
any doc (including old versions of this file) that still names them as live targets.

## Mirror every new `stack-*` command

Whenever a new `stack-*` command is added here (a fish function in
`~/.config/fish/functions/` plus its backing endpoint in `control-panel/app.py`), mirror it in
`StackMaster`:

- `../StackMaster/bin/bash/` **and** `../StackMaster/bin/zsh/`: the same command, generalized
  (no hardcoded IP/host paths; see `StackMaster/AGENTS.md`'s "Portability rules"), plus the
  matching endpoint ported into `StackMaster/control-panel/app.py`.

zsh matters here for a concrete reason, not just parity: this host's own interactive shell is
zsh (confirmed live 2026-07-21 - unquoted `$var` word-splitting silently doesn't happen the way
it does in bash, and `$status` is a reserved parameter that can't be assigned to, unlike
bash's `$?`-only convention). A bash-to-zsh port is not purely mechanical - see
`StackMaster/AGENTS.md`'s "Lessons-learned footnote" for more gotchas (e.g. never name a local
variable `path` in zsh, and `read -p` means something different there than in bash).

A `stack-*` command added only in this repo is not done; it is done when it exists in both
repos. The same applies to any structural change shared with `StackMaster`'s copies of
`docker-compose.full-stack.yml` or `control-panel/app.py` (a new service block, a new
`CONTAINER_LABELS`/`ARR_APPS`/similar dict entry) - check whether `StackMaster` needs the same
change before considering the work finished here.

**Known existing drift, not yours to fix unless asked**: as of 2026-07-21, `StackMaster`'s
`control-panel/app.py` still carries `recyclarr`/`beszel`/`beszel-agent` `CONTAINER_LABELS`
entries that this repo removed in v11.2.0, and its `docker-compose.full-stack.yml` likely has
the same services this repo no longer runs. That reconciliation is a separate, larger task -
don't assume `StackMaster` is fully current just because a specific change was mirrored there.
