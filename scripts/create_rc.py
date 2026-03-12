#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick helper to create a release candidate branch and bump version.

Actions performed:
 - Ensure we are in a git repo and on `develop` (unless --force)
 - Compute a release candidate as YY.M.N + rcN (default rc0)
 - Update core/pioreactor/version.py `__version__`
 - Commit the change
 - Create and push branch `release/<version>`
 - Switch back to `develop`
 - Print a pre-filled GitHub Releases URL and the matching update scripts folder

Usage examples:
  python3 scripts/create_rc.py                 # use the current YY.M series and rc0
  python3 scripts/create_rc.py --rc 1          # create rc1 for the same release
  python3 scripts/create_rc.py --series 26.3   # create an RC in an explicit YY.M series
  python3 scripts/create_rc.py --dry-run       # show actions only
  python3 scripts/create_rc.py --force         # skip branch/state checks

Note: this script invokes git. Run it manually when you are ready.
"""
import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "core" / "pioreactor" / "version.py"
UPDATE_SCRIPTS_DIR = REPO_ROOT / "core" / "update_scripts"
SERIES_PATTERN = re.compile(r"^\d{2}\.\d{1,2}$")
VERSION_PATTERN = re.compile(
    r"^(?P<yy>\d{2})\.(?P<month>\d{1,2})\.(?P<release>\d+)(?P<suffix>(?:\.dev\d+|rc\d+)?)$"
)


def run_git_command(args: list[str], dry_run: bool) -> None:
    cmd = ["git"] + args
    if dry_run:
        print(f"DRY-RUN: $ {' '.join(cmd)}")
        return
    subprocess.run(cmd, check=True)


def get_current_git_branch() -> str:
    return subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()


def assert_git_repo() -> None:
    try:
        inside = subprocess.check_output(["git", "rev-parse", "--is-inside-work-tree"], text=True).strip()
        if inside != "true":
            raise RuntimeError("Not inside a git repository.")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Not inside a git repository.") from exc


def ensure_clean_working_tree(allow_only_version_py_change: bool = True) -> None:
    out = subprocess.check_output(["git", "status", "--porcelain"], text=True)
    lines = [line for line in out.splitlines() if line.strip()]
    if not lines:
        return
    if allow_only_version_py_change:
        other = [line for line in lines if (VERSION_FILE.as_posix() not in line and "??" not in line)]
        if not other:
            return
    raise RuntimeError("Working tree has uncommitted changes. Commit or stash them first.")


def read_version_value() -> str:
    for line in VERSION_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=")[1].strip().strip('"')
    raise RuntimeError(f"Could not read __version__ from {VERSION_FILE}")


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


def compute_series(series_override: str | None = None) -> str:
    if series_override is not None:
        if SERIES_PATTERN.match(series_override) is None:
            raise ValueError("--series must be in format YY.M, e.g., 26.3")
        return series_override

    today = _dt.date.today()
    return f"{today.year % 100}.{today.month}"


def get_existing_tag_versions() -> list[str]:
    output = subprocess.check_output(["git", "tag", "--list"], text=True)
    versions: list[str] = []
    for line in output.splitlines():
        tag = line.strip()
        if VERSION_PATTERN.match(tag):
            versions.append(tag)
    return versions


def determine_release_base(series: str, current_version: str) -> str:
    _, _, current_release, _ = parse_version(current_version)
    highest_release = -1

    for version in get_existing_tag_versions():
        if get_version_series(version) == series:
            _, _, release, _ = parse_version(version)
            highest_release = max(highest_release, release)

    if get_version_series(current_version) == series and current_release > highest_release:
        next_release = current_release
    else:
        next_release = highest_release + 1

    return f"{series}.{next_release}"


def compute_rc_version(rc_index: int, series_override: str | None = None) -> tuple[str, str]:
    series = compute_series(series_override)
    base_version = determine_release_base(series, read_version_value())
    return base_version, f"{base_version}rc{rc_index}"


def update_version_py_to(version: str, dry_run: bool) -> None:
    src = VERSION_FILE.read_text(encoding="utf-8")
    new_src, count = re.subn(r'(__version__\s*=\s*")[^"]+("\s*)', rf"\g<1>{version}\2", src, count=1)
    if count == 0:
        raise RuntimeError(f"Could not find __version__ assignment in {VERSION_FILE}")
    if dry_run:
        print(f"DRY-RUN: would write {VERSION_FILE} with version={version}")
        return
    VERSION_FILE.write_text(new_src, encoding="utf-8")


def list_update_scripts_for(version_base: str) -> list[Path]:
    version_dir = UPDATE_SCRIPTS_DIR / version_base
    if not version_dir.exists() or not version_dir.is_dir():
        return []
    return sorted(path for path in version_dir.rglob("*") if path.is_file())


def build_github_release_url(version: str, branch: str) -> str:
    base = "https://github.com/pioreactor/pioreactor/releases/new"
    return f"{base}?tag={version}&target={branch}&title={version}&prerelease=1"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create a release candidate branch and bump version.")
    parser.add_argument("--rc", type=int, default=0, help="rc index (default: 0), e.g. --rc 1 -> rc1")
    parser.add_argument("--series", type=str, default=None, help="Override YY.M series, e.g. 26.3")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    parser.add_argument("--force", action="store_true", help="Skip branch and clean-tree checks")
    args = parser.parse_args(argv)

    try:
        assert_git_repo()
        version_base, version = compute_rc_version(args.rc, args.series)
        release_branch = f"release/{version}"

        current_branch = get_current_git_branch()
        if current_branch != "develop" and not args.force:
            print(
                f"Error: current branch is '{current_branch}', expected 'develop'. Use --force to continue."
            )
            return 2

        ensure_clean_working_tree()

        print(f"Creating release candidate for {version} (base={version_base})\n")

        run_git_command(["checkout", "develop"], dry_run=args.dry_run)

        update_version_py_to(version, dry_run=args.dry_run)
        run_git_command(["add", VERSION_FILE.as_posix()], dry_run=args.dry_run)
        run_git_command(["commit", "-m", "bump rc version"], dry_run=args.dry_run)

        run_git_command(["checkout", "-B", release_branch], dry_run=args.dry_run)
        run_git_command(["push", "origin", release_branch], dry_run=args.dry_run)

        run_git_command(["checkout", "develop"], dry_run=args.dry_run)

        gh_url = build_github_release_url(version, release_branch)
        update_files = list_update_scripts_for(version_base)

        print("\nNext steps on GitHub:")
        print(f" - Open: {gh_url}")
        print(f" - Tag: {version}")
        print(f" - Target: {release_branch}")
        print(f" - Title: {version}")
        print(" - Mark as a pre-release")
        if update_files:
            print(" - Attach update scripts:")
            for path in update_files:
                print(f"    * {path.relative_to(REPO_ROOT)}")
        else:
            print(f" - (No update scripts found for {version_base})")

        print("\nSuggested command to test update once published:")
        print(f"   pio update -v {version}")

        return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
