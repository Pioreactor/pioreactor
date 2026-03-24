#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automate the production release flow described in the ops runbook.

The script performs the local git tasks:
 - ensure repository state is suitable (on develop unless --force)
 - ensure version.py matches the target YY.M.N release (and bump if needed)
 - ensure CHANGELOG top entry matches the same YY.M.N release
 - move update scripts from core/update_scripts/upcoming to the YY.M.N folder
 - commit the release prep, merge into master, push master
 - merge back into develop and bump to the next YY.M.N.dev0

Usage examples:
  python3 scripts/create_release.py                  # release the current YY.M.N candidate
  python3 scripts/create_release.py --series 26.3    # release in an explicit YY.M series
  python3 scripts/create_release.py --dry-run        # print actions only
  python3 scripts/create_release.py --force          # skip branch check

Note: this script invokes git. Run it manually when you are ready.
"""
import argparse
import datetime as _dt
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "core" / "pioreactor" / "version.py"
CHANGELOG_FILE = REPO_ROOT / "CHANGELOG.md"
UPDATE_SCRIPTS_DIR = REPO_ROOT / "core" / "update_scripts"
FE_BUILD_DIR = REPO_ROOT / "core" / "pioreactor" / "web" / "static"
SERIES_PATTERN = re.compile(r"^\d{2}\.\d{1,2}$")
VERSION_PATTERN = re.compile(
    r"^(?P<yy>\d{2})\.(?P<month>\d{1,2})\.(?P<release>\d+)(?P<suffix>(?:\.dev\d+|rc\d+)?)$"
)
PRE_UPDATE_TEMPLATE = """#!/bin/bash

set -xeu

export LC_ALL=C

# Lower bound version
min_version="{min_version}"

# Get the current version of pio
current_version=$(sudo -u pioreactor -i pio version)

# Use sorting to determine if the current version is less than the minimum version
is_valid=$(printf "%s\\n%s" "$current_version" "$min_version" | sort -V | head -n1)

# If the smallest version isn't the minimum version, then current version is too low
if [ "$is_valid" != "$min_version" ]; then
    sudo -u pioreactor -i pio log -l ERROR -m "Version error: installed version $current_version is lower than the minimum required version $min_version."
    exit 1
fi

echo "Version check passed: $current_version"
"""


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


def compute_series(series_override: str | None = None) -> str:
    if series_override is not None:
        if SERIES_PATTERN.match(series_override) is None:
            raise ValueError("--series must be in format YY.M, e.g., 26.3")
        return series_override

    today = _dt.date.today()
    return f"{today.year % 100}.{today.month}"


def read_version_value() -> str:
    for line in VERSION_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=")[1].strip().strip('"')
    raise RuntimeError(f"Could not read __version__ from {VERSION_FILE}")


def write_version_value(version: str, dry_run: bool) -> None:
    src = VERSION_FILE.read_text(encoding="utf-8")
    lines: list[str] = []
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
    VERSION_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_version(version: str) -> tuple[int, int, int, str]:
    match = VERSION_PATTERN.match(version)
    if match is None:
        raise ValueError(f"Version {version!r} is not in the expected YY.M.N format.")
    return (
        int(match.group("yy")),
        int(match.group("month")),
        int(match.group("release")),
        match.group("suffix"),
    )


def get_version_series(version: str) -> str:
    yy, month, _, _ = parse_version(version)
    return f"{yy}.{month}"


def get_version_base(version: str) -> str:
    yy, month, release, _ = parse_version(version)
    return f"{yy}.{month}.{release}"


def increment_base_version(version: str) -> str:
    yy, month, release, _ = parse_version(version)
    return f"{yy}.{month}.{release + 1}"


def get_series_floor_version(version: str) -> str:
    yy, month, _, _ = parse_version(version)
    return f"{yy}.{month}.0"


def get_existing_tag_versions() -> list[str]:
    output = subprocess.check_output(["git", "tag", "--list"], text=True)
    versions: list[str] = []
    for line in output.splitlines():
        tag = line.strip()
        if VERSION_PATTERN.match(tag):
            versions.append(tag)
    return versions


def determine_release_base(series: str, current_version: str) -> str:
    current_base = get_version_base(current_version)
    current_series = get_version_series(current_version)
    highest_release = -1

    for version in get_existing_tag_versions():
        if get_version_series(version) == series:
            _, _, release, _ = parse_version(version)
            highest_release = max(highest_release, release)

    if current_series == series:
        _, _, current_release, suffix = parse_version(current_version)
        if suffix.startswith("rc") or suffix.startswith(".dev") or current_release > highest_release:
            return current_base

    return f"{series}.{highest_release + 1}"


def ensure_release_version(version: str, dry_run: bool) -> bool:
    current = read_version_value()
    if current == version:
        return False
    print(f"Updating __version__ from {current} -> {version}")
    write_version_value(version, dry_run)
    return True


def ensure_dev_version(version: str, dry_run: bool) -> bool:
    next_version = f"{increment_base_version(version)}.dev0"
    current = read_version_value()
    if current == next_version:
        return False
    print(f"Updating __version__ from {current} -> {next_version}")
    write_version_value(next_version, dry_run)
    return True


def ensure_changelog_top_matches(version: str, dry_run: bool) -> bool:
    text = CHANGELOG_FILE.read_text(encoding="utf-8").splitlines()
    try:
        first_idx, first_heading = next((idx, line) for idx, line in enumerate(text) if line.strip())
    except StopIteration as exc:
        raise RuntimeError("CHANGELOG.md appears to be empty.") from exc

    expected = f"### {version}"
    if first_heading == expected:
        return False

    print(f"Updating CHANGELOG heading from {first_heading!r} -> {expected!r}")
    if dry_run:
        print(f"DRY-RUN: would update {CHANGELOG_FILE}")
        return True

    text[first_idx] = expected
    CHANGELOG_FILE.write_text("\n".join(text) + "\n", encoding="utf-8")
    return True


def ensure_pre_update_script(version: str, dry_run: bool) -> bool:
    upcoming = UPDATE_SCRIPTS_DIR / "upcoming"
    pre_update_path = upcoming / "pre_update.sh"
    min_version = get_series_floor_version(version)
    expected = PRE_UPDATE_TEMPLATE.format(min_version=min_version)

    if pre_update_path.exists():
        current = pre_update_path.read_text(encoding="utf-8")
        if current == expected:
            return False
        print(f"Updating {pre_update_path} with minimum version {min_version}")
    else:
        print(f"Creating {pre_update_path} with minimum version {min_version}")

    if dry_run:
        print(f"DRY-RUN: would write {pre_update_path}")
        return True

    upcoming.mkdir(parents=True, exist_ok=True)
    pre_update_path.write_text(expected, encoding="utf-8")
    pre_update_path.chmod(0o755)
    return True


def ensure_update_scripts_folder(version: str, dry_run: bool) -> bool:
    target = UPDATE_SCRIPTS_DIR / version
    upcoming = UPDATE_SCRIPTS_DIR / "upcoming"
    if target.exists():
        return False
    pre_update_path = upcoming / "pre_update.sh"
    if not pre_update_path.exists():
        raise RuntimeError(f"Missing pre_update.sh in {upcoming}")
    print(f"Renaming update scripts: upcoming -> {version}")
    if not upcoming.exists():
        raise RuntimeError(f"Missing update scripts directory {upcoming}")
    if not any(upcoming.iterdir()):
        if dry_run:
            print(f"DRY-RUN: would create {target}")
            return True
        target.mkdir(parents=True, exist_ok=True)
        return True
    if dry_run:
        print(f"DRY-RUN: would move {upcoming} -> {target}")
        return True
    shutil.move(upcoming.as_posix(), target.as_posix())
    return True


def stage_if_exists(path: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY-RUN: $ git add -A {path.as_posix()}")
        return
    if path.is_dir() and path.name != "update_scripts":
        keep = path / ".gitkeep"
        if not any(path.iterdir()):
            keep.touch(exist_ok=True)
    if path.exists() or path.name == "update_scripts":
        subprocess.run(["git", "add", "-A", path.as_posix()], check=True)


def stage_update_scripts_changes(version: str, dry_run: bool) -> None:
    target = UPDATE_SCRIPTS_DIR / version
    upcoming = UPDATE_SCRIPTS_DIR / "upcoming"

    tracked_upcoming_paths = subprocess.check_output(
        ["git", "ls-files", upcoming.as_posix()],
        text=True,
    ).splitlines()
    paths_to_stage: list[str] = [target.as_posix()]

    if upcoming.exists():
        paths_to_stage.append(upcoming.as_posix())

    paths_to_stage.extend(tracked_upcoming_paths)

    unique_paths_to_stage: list[str] = []
    seen: set[str] = set()
    for path in paths_to_stage:
        if path not in seen:
            unique_paths_to_stage.append(path)
            seen.add(path)

    if dry_run:
        print(f"DRY-RUN: $ git add -A {' '.join(unique_paths_to_stage)}")
        return

    if target.exists() and target.is_dir() and not any(target.iterdir()):
        (target / ".gitkeep").touch(exist_ok=True)

    for path in unique_paths_to_stage:
        subprocess.run(["git", "add", "-A", path], check=True)


def ensure_frontend_build_is_up_to_date(dry_run: bool) -> bool:
    if dry_run:
        print("DRY-RUN: would run make frontend-build and verify static assets are clean")
        return False
    subprocess.run(["make", "frontend-build"], check=True)
    return True


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automate production release git workflow.")
    parser.add_argument("--series", help="Release series in YY.M format", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print intended actions without executing")
    parser.add_argument("--force", action="store_true", help="Skip branch check and dirty working tree guard")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        assert_git_repo()
        series = compute_series(args.series)
        release_version = determine_release_base(series, read_version_value())
        release_branch = f"release/{release_version}"

        current_branch = get_current_git_branch()
        if current_branch != "develop" and not args.force:
            print(
                f"Error: current branch is '{current_branch}', expected 'develop'. Use --force to continue."
            )
            return 2

        fe_build_changed = False
        if not args.force:
            ensure_clean_working_tree()
            fe_build_changed = ensure_frontend_build_is_up_to_date(dry_run=args.dry_run)

        print(f"Preparing production release for {release_version}\n")

        run_git_command(["checkout", "develop"], dry_run=args.dry_run)
        run_git_command(["checkout", "-B", release_branch], dry_run=args.dry_run)

        release_version_changed = ensure_release_version(release_version, dry_run=args.dry_run)
        changelog_changed = ensure_changelog_top_matches(release_version, dry_run=args.dry_run)
        pre_update_changed = ensure_pre_update_script(release_version, dry_run=args.dry_run)
        update_scripts_changed = ensure_update_scripts_folder(release_version, dry_run=args.dry_run)

        if release_version_changed:
            stage_if_exists(VERSION_FILE, dry_run=args.dry_run)
        if changelog_changed:
            stage_if_exists(CHANGELOG_FILE, dry_run=args.dry_run)
        if pre_update_changed or update_scripts_changed:
            stage_update_scripts_changes(release_version, dry_run=args.dry_run)
        if fe_build_changed:
            stage_if_exists(FE_BUILD_DIR, dry_run=args.dry_run)

        need_release_commit = args.dry_run and (
            release_version_changed
            or changelog_changed
            or pre_update_changed
            or update_scripts_changed
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

        dev_version_changed = ensure_dev_version(release_version, dry_run=args.dry_run)
        if dev_version_changed:
            stage_if_exists(VERSION_FILE, dry_run=args.dry_run)

        need_dev_commit = args.dry_run and dev_version_changed
        if not args.dry_run:
            need_dev_commit = git_diff_cached_has_changes()

        if need_dev_commit:
            run_git_command(["commit", "-m", "bump version to dev"], dry_run=args.dry_run)
        else:
            print("No changes detected for develop bump; skipping commit.")

        release_url = (
            "https://github.com/pioreactor/pioreactor/releases/new"
            f"?tag={release_version}&title={release_version}"
        )

        print("\nNext manual steps:")
        print(" - Create GitHub release with tag and title", release_version)
        print("   ", release_url)
        print(" - Attach update scripts if applicable")
        print(" - Announce to community once artifacts are ready")

        return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
