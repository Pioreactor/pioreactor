# -*- coding: utf-8 -*-
"""
Repair Python packages that were installed over each other.

Plugin installs used `pip install --ignore-installed`, which writes a dependency's newer files over the
installed copy without uninstalling it. That leaves two dist-info folders for one package: pip reports
the old version while the files on disk are the new one (for example Adafruit-Blinka 10 code under
9.1.0 metadata, which breaks ADC reads).

For each such package, uninstall every copy and reinstall the release's bundled wheel. Packages the
release doesn't bundle keep their newest copy, the one whose files are on disk, and lose the stale
metadata. Safe to re-run: a package with one copy is left alone.

usage: python repair_duplicate_python_packages.py <dir of bundled wheels>
"""
import re
import shutil
import subprocess
import sys
import sysconfig
from collections import defaultdict
from pathlib import Path


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def main(wheels_dir: Path) -> None:
    site_packages = Path(sysconfig.get_paths()["purelib"])
    copies: dict[str, list[Path]] = defaultdict(list)
    for dist_info in site_packages.glob("*.dist-info"):
        name = dist_info.name.removesuffix(".dist-info").rsplit("-", 1)[0]
        copies[canonical(name)].append(dist_info)

    bundled = {canonical(wheel.name.split("-")[0]) for wheel in wheels_dir.glob("*.whl")}
    pip = [sys.executable, "-m", "pip"]

    for name, dist_infos in sorted(copies.items()):
        if len(dist_infos) < 2:
            continue
        print(f"Repairing {name}: {', '.join(sorted(d.name for d in dist_infos))}")
        if name in bundled:
            for _ in dist_infos:
                subprocess.run([*pip, "uninstall", "-y", name], check=True)
            subprocess.run(
                [*pip, "install", "--no-index", "--find-links", str(wheels_dir), "--no-deps", name],
                check=True,
            )
        else:
            newest = max(dist_infos, key=lambda dist_info: dist_info.stat().st_mtime)
            for stale in dist_infos:
                if stale != newest:
                    shutil.rmtree(stale)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
