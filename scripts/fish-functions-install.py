#!/usr/bin/env python3
"""Install this repo's fish functions into the user's fish function directory
as symlinks.

Phase 8a of docs/superpowers/specs/2026-08-13-cli-naming-cleanup-design.md.

Before this, fish-functions/ was hand-copied to ~/.config/fish/functions/ and
the two drifted 9 names apart - 4 functions existed only in the repo, 5 only
on the host. Symlinks remove the possibility rather than the habit.

Only files matching stack-*.fish are managed. Everything else in the target
directory belongs to the user, including __stack_api.fish, and is never
touched - it is the one directory where deleting the wrong file destroys work
with no other copy.

Usage:
    fish-functions-install.py [--dry-run] [--repo-dir DIR] [--installed-dir DIR]
"""
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_REPO_DIR = Path(__file__).resolve().parent.parent / "fish-functions"
DEFAULT_INSTALLED_DIR = Path.home() / ".config/fish/functions"
MANAGED_GLOB = "stack-*.fish"


def plan(repo_dir: Path, installed_dir: Path) -> dict:
    """Decide what to do without doing it.

    Returns four disjoint lists of paths in `installed_dir`: link (nothing
    there yet), relink (something there that is not the right link), prune
    (managed name with no repo source), keep (already correct).
    """
    actions: dict[str, list[Path]] = {"link": [], "relink": [], "prune": [], "keep": []}
    sources = {path.name: path for path in sorted(repo_dir.glob(MANAGED_GLOB))}

    for name, source in sources.items():
        target = installed_dir / name
        if not target.is_symlink() and not target.exists():
            actions["link"].append(target)
        elif target.is_symlink() and target.exists() and target.resolve() == source.resolve():
            actions["keep"].append(target)
        else:
            # A plain copy, or a link pointing somewhere else.
            actions["relink"].append(target)

    for target in sorted(installed_dir.glob(MANAGED_GLOB)):
        if target.name not in sources:
            actions["prune"].append(target)
    # A dangling symlink is not matched by glob() on some Python versions;
    # iterate the directory directly so a link to a deleted source is caught.
    for target in sorted(installed_dir.iterdir()):
        if (target.is_symlink() and not target.exists()
                and target.name.startswith("stack-") and target.name.endswith(".fish")
                and target.name not in sources and target not in actions["prune"]):
            actions["prune"].append(target)

    return actions


def apply(actions: dict, repo_dir: Path = DEFAULT_REPO_DIR, dry_run: bool = False) -> list[str]:
    """Perform the planned actions. Returns one description line per action.

    `repo_dir` is explicit rather than read from the module default so the
    tests can drive this against a tmp_path repo - and so a caller can never
    plan against one directory and apply against another.
    """
    lines: list[str] = []

    for target in actions["link"] + actions["relink"]:
        source = repo_dir / target.name
        verb = "link" if target in actions["link"] else "relink"
        lines.append(f"{verb}  {target} -> {source}")
        if dry_run:
            continue
        if target.is_symlink() or target.exists():
            target.unlink()
        target.symlink_to(source)

    for target in actions["prune"]:
        lines.append(f"prune  {target}")
        if not dry_run:
            target.unlink()

    lines.append(f"keep   {len(actions['keep'])} already-correct link(s)")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    parser.add_argument("--installed-dir", type=Path, default=DEFAULT_INSTALLED_DIR)
    args = parser.parse_args()

    args.installed_dir.mkdir(parents=True, exist_ok=True)
    for line in apply(plan(args.repo_dir, args.installed_dir),
                      repo_dir=args.repo_dir, dry_run=args.dry_run):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
