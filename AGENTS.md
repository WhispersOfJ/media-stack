# AGENTS.md

Guidance for AI coding agents (Claude Code or otherwise) working in this repo. See
`CLAUDE.md` first for architecture orientation, common commands, and the non-obvious facts
that span multiple files — this file covers what `CLAUDE.md` doesn't: the sync obligations
this repo has to its two downstream siblings.

## This repo has two downstream siblings that need to stay in sync

- **`../Stackalicious`** — the public, sanitized mirror. Every version bump here gets a
  matching `Sync: vX.Y.Z-vA.B.C` commit there (see that repo's own `AGENTS.md` for the
  sanitization rule - real LAN IP and host username must never appear in anything pushed
  there).
- **`../StackScripts`** — the standalone, redistributable CLI + control panel, generalized
  (installer-driven credentials, no hardcoded IP/paths) so someone running a similarly-shaped
  stack can use it without cloning this repo at all.

## The rule that matters most: mirror every new `stack-*` command

**Whenever a new `stack-*` command is added here** (a new fish function in
`~/.dotfiles/.config/fish/functions/` plus its backing endpoint in
`control-panel/app.py`), **it needs to be mirrored in both siblings**, not just documented
here:

1. `../Stackalicious/scripts/stack-cli/bash/` — bash port, matching this repo's own existing
   convention there.
2. `../StackScripts/bin/bash/` — same command, generalized (no hardcoded IP/host paths -
   see `StackScripts/AGENTS.md`'s "Portability rules" section) plus the matching endpoint
   ported into `StackScripts/control-panel/app.py`.

**Both siblings' CLIs are bash-only** — the parallel zsh ports (`StackScripts/bin/zsh/`,
`Stackalicious/scripts/stack-cli/zsh/`, 79 files total) were deleted after confirming 100%
command parity between the two shells (and, for what it's worth as background even though
fish isn't part of these two repos, the private fish functions here match too). Don't
re-introduce a zsh branch for a new command without a real reason to bring zsh back as a
supported shell.

This applies in the other direction too: a bug found and fixed in bash's version should be
checked for in every other repo's bash version, not just the one it was caught in. Historical
note: back when both a bash and zsh port existed, a `set -u` unbound-parameter bug and zsh's
`read -p` gotcha (silently meaning "read from a coprocess" instead of "show a prompt," never
populating the confirmation variable in `stack-restart-all.zsh`) both bit this exact codebase
- see `StackScripts/AGENTS.md`'s "lessons learned" for the fuller writeup. They no longer
apply to live code now that zsh is gone, but the underlying lesson (shells that look
POSIX-compatible on the surface can silently diverge on builtins) is worth keeping in mind
for bash itself too.

Treat "I added a `stack-*` command" and "I added a `stack-*` command in all three repos" as
the same task, not two separate ones - a command that only exists here isn't actually done
yet, it's half-shipped.
