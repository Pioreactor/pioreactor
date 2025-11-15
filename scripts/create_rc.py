#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick helper to create a release candidate branch and bump version.

Actions performed:
 - Ensure we are in a git repo and on `develop` (unless --force)
 - Compute CalVer as YY.M.D + rcN (default rc0) with no zero-padding
 - Update core/pioreactor/version.py `__version__`
 - Commit the change
 - Create and push branch `release/<version>`
 - Switch back to `develop`
 - Print a pre-filled GitHub Releases URL and the CHANGELOG section

Usage examples:
  python3 scratch/create_rc.py                 # use today and rc0
  python3 scratch/create_rc.py --rc 1          # create rc1
  python3 scratch/create_rc.py --dry-run       # show actions only
  python3 scratch/create_rc.py --force         # skip branch/state checks

Note: This script intentionally uses git, but does not run it during
agent execution. Run it locally when you are ready.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "core" / "pioreactor" / "version.py"
CHANGELOG_FILE = REPO_ROOT / "CHANGELOG.md"
UPDATE_SCRIPTS_DIR = REPO_ROOT / "core" / "update_scripts"


def run_git_command(args: list[str], dry_run: bool) -> None:
    cmd = ["git"] + args
    if dry_run:
        print(f"DRY-RUN: $ {' '.join(cmd)}")
        return
    subprocess.run(cmd, check=True)


def get_current_git_branch() -> str:
    out = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    return out


def assert_git_repo() -> None:
    try:
        inside = subprocess.check_output(["git", "rev-parse", "--is-inside-work-tree"], text=True).strip()
        if inside != "true":
            raise RuntimeError("Not inside a git repository.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError("Not inside a git repository.") from e


def ensure_clean_working_tree(allow_only_version_py_change: bool = True) -> None:
    out = subprocess.check_output(["git", "status", "--porcelain"], text=True)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if not lines:
        return
    if allow_only_version_py_change:
        other = [ln for ln in lines if (VERSION_FILE.as_posix() not in ln and "??" not in ln)]
        if not other:
            return
    raise RuntimeError("Working tree has uncommitted changes. Commit or stash them first.")


def compute_rc_version(rc_index: int, date_override: str | None = None) -> tuple[str, str]:
    """Return (calver, full_version).

    calver format: YY.M.D (no zero padding)
    full_version: f"{calver}rc{rc_index}"
    """
    if date_override:
        # Expecting format like '25.8.12'
        if not re.match(r"^\d{2}\.\d{1,2}\.\d{1,2}$", date_override):
            raise ValueError("--date must be in format YY.M.D, e.g., 25.8.12")
        calver = date_override
    else:
        now = _dt.date.today()
        calver = f"{now.year % 100}.{now.month}.{now.day}"
    version = f"{calver}rc{rc_index}"
    return calver, version


def update_version_py_to(version: str, dry_run: bool) -> None:
    src = VERSION_FILE.read_text()
    new_src, count = re.subn(r'(__version__\s*=\s*")[^"]+("\s*)', rf"\g<1>{version}\2", src, count=1)
    if count == 0:
        raise RuntimeError(f"Could not find __version__ assignment in {VERSION_FILE}")
    if dry_run:
        print(f"DRY-RUN: would write {VERSION_FILE} with version={version}")
        return
    VERSION_FILE.write_text(new_src)



def list_update_scripts_for(calver: str) -> list[Path]:
    d = UPDATE_SCRIPTS_DIR / "upcoming"
    if not d.exists() or not d.is_dir():
        return []
    files = sorted([p for p in d.rglob("*") if p.is_file()])
    return files


def build_github_release_url(version: str, branch: str) -> str:
    base = "https://github.com/pioreactor/pioreactor/releases/new"
    # Pre-fill tag, target, and title
    return f"{base}?tag={version}&target={branch}&title={version}&prerelease=1"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create a release candidate branch and bump version.")
    parser.add_argument("--rc", type=int, default=0, help="rc index (default: 0) e.g., --rc 1 -> rc1")
    parser.add_argument("--date", type=str, default=None, help="Override date in YY.M.D, e.g., 25.8.12")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    parser.add_argument("--force", action="store_true", help="Skip branch and clean-tree checks")
    args = parser.parse_args(argv)

    try:
        assert_git_repo()
        calver, version = compute_rc_version(args.rc, args.date)
        release_branch = f"release/{version}"

        current_branch = get_current_git_branch()
        if current_branch != "develop" and not args.force:
            print(
                f"Error: current branch is '{current_branch}', expected 'develop'. Use --force to continue."
            )
            return 2

        ensure_clean_working_tree()

        print(f"Creating release candidate for {version} (calver={calver})\n")

        # Ensure we start from develop
        run_git_command(["checkout", "develop"], dry_run=args.dry_run)

        # Update version.py
        update_version_py_to(version, dry_run=args.dry_run)
        run_git_command(["add", VERSION_FILE.as_posix()], dry_run=args.dry_run)
        run_git_command(["commit", "-m", "bump rc version"], dry_run=args.dry_run)

        # Create release branch and push
        run_git_command(["checkout", "-B", release_branch], dry_run=args.dry_run)
        run_git_command(["push", "origin", release_branch], dry_run=args.dry_run)

        # Back to develop
        run_git_command(["checkout", "develop"], dry_run=args.dry_run)

        # Prepare helpful output
        gh_url = build_github_release_url(version, release_branch)
        update_files = list_update_scripts_for(calver)

        print("\nNext steps on GitHub:")
        print(f" - Open: {gh_url}")
        print(f" - Tag: {version}")
        print(f" - Target: {release_branch}")
        print(f" - Title: {version}")
        print(" - Mark as a pre-release")
        if update_files:
            print(" - Attach update scripts:")
            for p in update_files:
                print(f"    * {p.relative_to(REPO_ROOT)}")
        else:
            print(" - (No update scripts found for this version)")

        print("\nSuggested command to test update once published:")
        print(f"   pio update -v {version}")

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
