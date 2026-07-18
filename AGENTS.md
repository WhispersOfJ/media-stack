# AGENTS.md

Guidance for AI coding agents working in this repo. Read `CLAUDE.md` first for architecture
orientation, common commands, and facts that span multiple files. This file covers the sync
obligations to this repo's two downstream siblings.

## Downstream siblings

- **`../Stackalicious`**: the public, sanitized mirror. Every version bump here gets a
  matching `Sync: vX.Y.Z-vA.B.C` commit there. Sanitization rule (see that repo's
  `AGENTS.md`): the real LAN IP and host username must never appear in anything pushed there.
- **`../StackScripts`**: the standalone, redistributable CLI + control panel, generalized
  (installer-driven credentials, no hardcoded IP/paths) for use without cloning this repo.

## Mirror every new `stack-*` command

Whenever a new `stack-*` command is added here (a fish function in
`~/.dotfiles/.config/fish/functions/` plus its backing endpoint in `control-panel/app.py`),
mirror it in both siblings:

1. `../Stackalicious/scripts/stack-cli/bash/` **and** `../Stackalicious/scripts/stack-cli/zsh/`:
   bash and zsh ports, matching the existing convention there.
2. `../StackScripts/bin/bash/` **and** `../StackScripts/bin/zsh/`: the same command, generalized
   (no hardcoded IP/host paths; see `StackScripts/AGENTS.md`'s "Portability rules"), plus the
   matching endpoint ported into `StackScripts/control-panel/app.py`.

**Correction (2026-07-18): zsh is back.** Both siblings' CLIs were bash-only from the point the
parallel zsh ports (79 files across both repos) were deleted after confirming command parity,
until a user need for zsh came back and both repos re-added `.../zsh/` in full. A new
`stack-*` command needs both a bash and a zsh port in each sibling - shellcheck covers the bash
side; the zsh side gets its own `zsh -n` syntax-check pass in each repo's CI (see either
sibling's own workflow file) since shellcheck doesn't understand zsh syntax. See each sibling's
own `AGENTS.md` "Lessons-learned footnote" for zsh-specific gotchas (a bash-to-zsh port is not
purely mechanical - e.g. never name a local variable `path` in zsh, and `read -p` means
something different there than in bash).

The rule runs in both directions: a bug found in one repo's bash version should be checked
for in every other repo's bash version. Historical examples from when the zsh ports existed:
a `set -u` unbound-parameter crash in the shared API helper, and zsh's `read -p` meaning
"read from a coprocess" rather than "show a prompt" (never populating the confirmation
variable in `stack-restart-all.zsh`). See `StackScripts/AGENTS.md`'s "lessons learned".
Shells that look POSIX-compatible can diverge on builtins.

A `stack-*` command added only in this repo is not done; it is done when it exists in all
three repos.
