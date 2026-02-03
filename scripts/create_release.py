#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automate the production release flow described in the ops runbook.

The script performs the local git tasks:
 - ensure repository state is suitable (on develop unless --force)
 - ensure version.py matches the CalVer date (and bump if needed)
 - ensure CHANGELOG top entry matches the same CalVer
 - move update scripts from core/update_scripts/upcoming to the CalVer folder
 - commit the release prep, merge into master, push master
 - merge back into develop and append .dev0 to __version__

Usage examples:
  python3 scratch/create_release.py                  # run with today's date
  python3 scratch/create_release.py --date 25.9.18   # use explicit CalVer
  python3 scratch/create_release.py --dry-run        # print actions only
  python3 scratch/create_release.py --force          # skip branch check

Note: this script invokes git. Run it manually when you are ready.
"""
import argparse
import datetime as _dt
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "core" / "pioreactor" / "version.py"
CHANGELOG_FILE = REPO_ROOT / "CHANGELOG.md"
UPDATE_SCRIPTS_DIR = REPO_ROOT / "core" / "update_scripts"
FE_BUILD_DIR = REPO_ROOT / "core" / "pioreactor" / "web" / "static"


def run_git_command(args: list[str], dry_run: bool) -> None:
    cmd = ["git"] + args
    if dry_run:
        print(f"DRY-RUN: $ {' '.join(cmd)}")
        return
    subprocess.run(cmd, check=True)


def git_diff_cached_has_changes() -> bool:
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
    return result.returncode == 1


def assert_git_repo() -> None:
    try:
        inside = subprocess.check_output(["git", "rev-parse", "--is-inside-work-tree"], text=True).strip()
        if inside != "true":
            raise RuntimeError("Not inside a git repository.")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Not inside a git repository.") from exc


def get_current_git_branch() -> str:
    return subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()


def ensure_clean_working_tree() -> None:
    status = subprocess.check_output(["git", "status", "--porcelain"], text=True)
    dirty = [line for line in status.splitlines() if (line.strip() and not line.strip().startswith("??"))]
    if dirty:
        raise RuntimeError("Working tree has uncommitted changes. Commit or stash them first.")


def compute_calver(date_override: str | None) -> str:
    if date_override:
        parts = date_override.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise ValueError("--date must be in format YY.M.D, e.g., 25.9.18")
        return date_override
    today = _dt.date.today()
    return f"{today.year % 100}.{today.month}.{today.day}"


def read_version_value() -> str:
    for line in VERSION_FILE.read_text().splitlines():
        if line.startswith("__version__"):
            return line.split("=")[1].strip().strip('"')
    raise RuntimeError(f"Could not read __version__ from {VERSION_FILE}")


def write_version_value(version: str, dry_run: bool) -> None:
    src = VERSION_FILE.read_text()
    lines = []
    updated = False
    for line in src.splitlines():
        if line.startswith("__version__") and not updated:
            lines.append(f'__version__ = "{version}"')
            updated = True
        else:
            lines.append(line)
    if not updated:
        raise RuntimeError(f"Could not find __version__ assignment in {VERSION_FILE}")
    if dry_run:
        print(f"DRY-RUN: would write {VERSION_FILE} with version={version}")
        return
    VERSION_FILE.write_text("\n".join(lines) + "\n")


def ensure_release_version(calver: str, dry_run: bool) -> bool:
    current = read_version_value()
    if current == calver:
        return False
    print(f"Updating __version__ from {current} -> {calver}")
    write_version_value(calver, dry_run)
    return True


def ensure_dev_version(calver: str, dry_run: bool) -> bool:
    next_version = f"{calver}.dev0"
    current = read_version_value()
    if current == next_version:
        return False
    print(f"Updating __version__ from {current} -> {next_version}")
    write_version_value(next_version, dry_run)
    return True


def ensure_changelog_top_matches(calver: str, dry_run: bool) -> bool:
    text = CHANGELOG_FILE.read_text().splitlines()
    try:
        first_idx, first_heading = next((idx, line) for idx, line in enumerate(text) if line.strip())
    except StopIteration as exc:
        raise RuntimeError("CHANGELOG.md appears to be empty.") from exc

    expected = f"### {calver}"
    if first_heading == expected:
        return False

    print(f"Updating CHANGELOG heading from {first_heading!r} -> {expected!r}")
    if dry_run:
        print(f"DRY-RUN: would update {CHANGELOG_FILE}")
        return True

    text[first_idx] = expected
    CHANGELOG_FILE.write_text("\n".join(text) + "\n")
    return True


def ensure_update_scripts_folder(calver: str, dry_run: bool) -> bool:
    target = UPDATE_SCRIPTS_DIR / calver
    upcoming = UPDATE_SCRIPTS_DIR / "upcoming"
    if target.exists():
        return False
    if upcoming.exists():
        pre_update_path = upcoming / "pre_update.sh"
        if not pre_update_path.exists():
            raise RuntimeError(f"Missing pre_update.sh in {upcoming}")
        print(f"Renaming update scripts: upcoming -> {calver}")
        run_git_command(["mv", upcoming.as_posix(), target.as_posix()], dry_run)
        return True
    print("No upcoming update scripts folder found; skipping rename.")
    return False


def ensure_pre_update_script_exists(calver: str, update_scripts_changed: bool, dry_run: bool) -> bool:
    target = UPDATE_SCRIPTS_DIR / calver
    upcoming = UPDATE_SCRIPTS_DIR / "upcoming"

    if target.exists() or update_scripts_changed:
        target_dir = target
    elif upcoming.exists():
        target_dir = upcoming
    else:
        print("No update scripts directory found to ensure pre_update.sh; skipping.")
        return False

    pre_update_path = target_dir / "pre_update.sh"
    if pre_update_path.exists():
        return False

    print(f"Creating missing pre_update.sh in {target_dir}")
    if dry_run:
        print(f"DRY-RUN: would write {pre_update_path}")
        return True

    pre_update_path.write_text("#!/bin/bash\n\n" "set -euo pipefail\n\n" "# Intentionally left blank.\n")
    return True


def stage_if_exists(path: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY-RUN: $ git add {path.as_posix()}")
        return
    if path.exists() or path.name == "update_scripts":
        subprocess.run(["git", "add", path.as_posix()], check=True)


def ensure_frontend_build_is_up_to_date(dry_run: bool) -> bool:
    if dry_run:
        print("DRY-RUN: would run make frontend-build and verify static assets are clean")
        return False
    subprocess.run(["make", "frontend-build"], check=True)
    return True


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automate production release git workflow.")
    parser.add_argument("--date", help="CalVer date in YY.M.D format", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print intended actions without executing")
    parser.add_argument("--force", action="store_true", help="Skip branch check and dirty working tree guard")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        assert_git_repo()
        calver = compute_calver(args.date)
        release_branch = f"release/{calver}"

        current_branch = get_current_git_branch()
        if current_branch != "develop" and not args.force:
            print(
                f"Error: current branch is '{current_branch}', expected 'develop'. Use --force to continue."
            )
            return 2

        if not args.force:
            ensure_clean_working_tree()
            fe_build_changed = ensure_frontend_build_is_up_to_date(dry_run=args.dry_run)

        print(f"Preparing production release for {calver}\n")

        run_git_command(["checkout", "develop"], dry_run=args.dry_run)
        run_git_command(["checkout", "-B", release_branch], dry_run=args.dry_run)

        release_version_changed = ensure_release_version(calver, dry_run=args.dry_run)
        changelog_changed = ensure_changelog_top_matches(calver, dry_run=args.dry_run)
        update_scripts_changed = ensure_update_scripts_folder(calver, dry_run=args.dry_run)
        pre_update_created = ensure_pre_update_script_exists(
            calver, update_scripts_changed=update_scripts_changed, dry_run=args.dry_run
        )

        if release_version_changed:
            stage_if_exists(VERSION_FILE, dry_run=args.dry_run)
        if changelog_changed:
            stage_if_exists(CHANGELOG_FILE, dry_run=args.dry_run)
        if update_scripts_changed or pre_update_created:
            stage_if_exists(UPDATE_SCRIPTS_DIR, dry_run=args.dry_run)
        if fe_build_changed:
            stage_if_exists(FE_BUILD_DIR, dry_run=args.dry_run)

        need_release_commit = args.dry_run and (
            release_version_changed
            or changelog_changed
            or update_scripts_changed
            or pre_update_created
            or fe_build_changed
        )
        if not args.dry_run:
            need_release_commit = git_diff_cached_has_changes()

        if need_release_commit:
            run_git_command(["commit", "-m", "bump version"], dry_run=args.dry_run)
        else:
            print("No changes detected for release prep commit; skipping commit.")

        run_git_command(["checkout", "master"], dry_run=args.dry_run)
        run_git_command(["merge", release_branch], dry_run=args.dry_run)
        run_git_command(["push", "origin", "master"], dry_run=args.dry_run)

        run_git_command(["checkout", "develop"], dry_run=args.dry_run)
        run_git_command(["merge", release_branch], dry_run=args.dry_run)

        dev_version_changed = ensure_dev_version(calver, dry_run=args.dry_run)
        if dev_version_changed:
            stage_if_exists(VERSION_FILE, dry_run=args.dry_run)

        need_dev_commit = args.dry_run and dev_version_changed
        if not args.dry_run:
            need_dev_commit = git_diff_cached_has_changes()

        if need_dev_commit:
            run_git_command(["commit", "-m", "bump version to dev"], dry_run=args.dry_run)
        else:
            print("No changes detected for develop bump; skipping commit.")

        release_url = "https://github.com/pioreactor/pioreactor/releases/new" f"?tag={calver}&title={calver}"

        print("\nNext manual steps:")
        print(" - Create GitHub release with tag and title", calver)
        print("   ", release_url)
        print(" - Attach update scripts if applicable")
        print(" - Announce to community once artifacts are ready")

        return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
