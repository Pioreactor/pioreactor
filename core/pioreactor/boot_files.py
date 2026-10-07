# -*- coding: utf-8 -*-
"""Import supported YAML assets staged on the Raspberry Pi boot partition."""
import grp
import os
import pwd
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from msgspec.yaml import decode as yaml_decode
from pioreactor.experiment_profiles.profile_struct import Profile
from pioreactor.experiment_profiles.validate import validate_profile
from pioreactor.structs import Model


def validate_asset(relative: Path, content: bytes) -> None:
    category = relative.parts[0]
    if category == "experiment_profiles":
        result = validate_profile(yaml_decode(content, type=Profile))
        if not result.ok:
            raise ValueError("; ".join(f"{d.path}: {d.message}" for d in result.diagnostics))
    elif category == "models":
        yaml_decode(content, type=Model)
    elif category == "hardware":
        # Hardware layers are partial mappings, merged and checked by the runtime.
        if not isinstance(yaml_decode(content), dict):
            raise ValueError("Hardware YAML must contain a mapping")


def import_files(boot_dir: Path, data_dir: Path, is_leader: bool, owner: tuple[int, int]) -> int:
    """Replace validated assets without backups; retain failed inputs for retry."""
    failures = 0
    for category in ("experiment_profiles", "models", "hardware"):
        if category == "experiment_profiles" and not is_leader:
            continue
        source_dir = boot_dir / category
        files = source_dir.rglob("*") if category == "hardware" else source_dir.glob("*")
        for source in sorted(files):
            if source.suffix not in (".yaml", ".yml"):
                continue
            relative = source.relative_to(boot_dir)
            diagnostic = source.with_name(source.name + ".log")
            temporary: Path | None = None
            try:
                # The FAT boot partition cannot contain symlinks.
                if not source.is_file():
                    continue
                content = source.read_bytes()
                validate_asset(relative, content)
                destination = data_dir / relative
                parent = destination.parent
                # Reject destination symlinks rather than following them outside the data root.
                directory = data_dir
                for part in relative.parent.parts:
                    directory = directory / part
                    if directory.is_symlink():
                        raise ValueError("Symlink destination directories are not supported")
                    if not directory.exists():
                        directory.mkdir(mode=0o2775)
                        os.chown(directory, *owner)
                        directory.chmod(0o2775)
                with NamedTemporaryFile(dir=parent, prefix=".bootfs-", delete=False) as output:
                    temporary = Path(output.name)
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
                os.chown(temporary, *owner)
                temporary.chmod(0o664)
                temporary.replace(destination)
                source.unlink()
                diagnostic.unlink(missing_ok=True)
                print(f"Imported {relative}", flush=True)
            except Exception as error:
                # One bad external file must not prevent independent assets from importing.
                failures += 1
                message = f"Failed to import {relative}: {error}\n"
                print(message, file=sys.stderr, end="", flush=True)
                try:
                    diagnostic.write_text(message, encoding="utf-8")
                except OSError as log_error:
                    print(f"Could not write {diagnostic}: {log_error}", file=sys.stderr)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    return failures


def main() -> None:
    failures = import_files(
        Path("/boot/firmware/pioreactor"),
        Path(os.environ.get("DOT_PIOREACTOR", "/home/pioreactor/.pioreactor")),
        sys.argv[1] == "leader",
        (pwd.getpwnam("pioreactor").pw_uid, grp.getgrnam("www-data").gr_gid),
    )
    sys.exit(bool(failures))


if __name__ == "__main__":
    main()
