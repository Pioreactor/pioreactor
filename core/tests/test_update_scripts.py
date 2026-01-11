# -*- coding: utf-8 -*-
from pathlib import Path
from typing import Generator


SCRIPT_DIRECTORY = Path(__file__).resolve().parent.parent / "update_scripts" / "upcoming"


def find_sql_scripts(directory: str | Path) -> Generator[Path, None, None]:
    """Recursively find all SQL script files in the specified directory."""
    for sql_file in Path(directory).rglob("*.sql"):
        if sql_file.is_file():
            yield sql_file


def find_shell_scripts(directory: str | Path) -> Generator[Path, None, None]:
    """Recursively find all shell script files in the specified directory."""
    types = {"update.sh", "pre_update.sh", "post_update.sh"}
    for script_file in Path(directory).rglob("*"):
        if script_file.is_file() and script_file.name in types:
            yield script_file


def test_pio_commands() -> None:
    scripts = find_shell_scripts(SCRIPT_DIRECTORY)
    error_msgs = []

    for script in scripts:
        with open(script, "r") as file:
            for line_number, line in enumerate(file, start=1):
                if line.lstrip().startswith("#"):  # comment
                    continue

                # Checking for 'pio' not preceded by 'sudo -u pioreactor -i'
                if (" pio " in line or line.strip().startswith("pio ")) and (
                    "sudo -u pioreactor -i" not in line
                ):
                    error_msgs.append(
                        f"Error in {script} at line {line_number}: 'pio' command must be prefixed with 'sudo -u pioreactor -i'."
                    )

    assert not error_msgs, "\n".join(error_msgs)


def test_sql_scripts_start_with_our_PRAGMA() -> None:
    scripts = find_sql_scripts(SCRIPT_DIRECTORY)
    error_msgs = []

    for script in scripts:
        with open(script, "r") as file:
            first_line = file.readline().strip()
            if not first_line.startswith("PRAGMA"):
                error_msgs.append(f"Error in {script}: SQL scripts must start with a PRAGMA statement.")

    assert not error_msgs, "\n".join(error_msgs)


def test_no_restarting_huey_service() -> None:
    # this can mess with updating if we interrupt huey.
    scripts = find_shell_scripts(SCRIPT_DIRECTORY)
    error_msgs = []

    for script in scripts:
        with open(script, "r") as file:
            for line_number, line in enumerate(file, start=1):
                if line.lstrip().startswith("#"):  # comment
                    continue

                # Checking for 'systemctl restart huey'
                if "systemctl restart huey" in line or "systemctl restart pioreactor-web" in line:
                    error_msgs.append(
                        f"Error in {script} at line {line_number}: 'systemctl restart huey' should not be used since it will halt updates."
                    )

    assert not error_msgs, "\n".join(error_msgs)
