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

1. `../Stackalicious/scripts/stack-cli/{bash,zsh}/` — bash and zsh ports, matching this
   repo's own existing convention there.
2. `../StackScripts/bin/{bash,zsh}/` — same command, generalized (no hardcoded IP/host
   paths - see `StackScripts/AGENTS.md`'s "Portability rules" section) plus the matching
   endpoint ported into `StackScripts/control-panel/app.py`.

This applies in the other direction too: a bug found and fixed in one shell's version (the
`set -u` unbound-parameter bug and zsh's `read -p` gotcha have both bitten this exact
codebase before - see `StackScripts/AGENTS.md`) should be checked for in every other
shell's version, in every one of these three repos, not just the one it was caught in.

Treat "I added a `stack-*` command" and "I added a `stack-*` command in all three repos" as
the same task, not two separate ones - a command that only exists here isn't actually done
yet, it's half-shipped.
