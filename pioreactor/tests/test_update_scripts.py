# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from typing import Generator


def find_sql_scripts(directory: str) -> Generator[str, None, None]:
    """Recursively find all SQL script files in the specified directory."""
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".sql"):
                yield os.path.join(root, file)


def find_shell_scripts(directory: str) -> Generator[str, None, None]:
    """Recursively find all shell script files in the specified directory."""
    types = {"update.sh", "pre_update.sh", "post_update.sh"}
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file in types:
                yield os.path.join(root, file)


def test_pio_commands() -> None:
    script_directory = "update_scripts"
    scripts = find_shell_scripts(script_directory)
    error_msgs = []

    for script in scripts:
        with open(script, "r") as file:
            for line_number, line in enumerate(file, start=1):
                if line.lstrip().startswith("#"):  # comment
                    continue

                # Checking for 'pio' not preceded by 'su -u pioreactor'
                if (" pio " in line or line.strip().startswith("pio ")) and "sudo -u pioreactor" not in line:
                    error_msgs.append(
                        f"Error in {script} at line {line_number}: 'pio' command must be prefixed with 'sudo -u pioreactor'."
                    )

    assert not error_msgs, "\n".join(error_msgs)


def test_sql_scripts_start_with_our_PRAGMA() -> None:
    script_directory = "update_scripts/upcoming"
    scripts = find_sql_scripts(script_directory)
    error_msgs = []

    for script in scripts:
        with open(script, "r") as file:
            first_line = file.readline().strip()
            if not first_line.startswith("PRAGMA"):
                error_msgs.append(f"Error in {script}: SQL scripts must start with a PRAGMA statement.")

    assert not error_msgs, "\n".join(error_msgs)


def test_no_restarting_huey_service() -> None:
    # this can mess with updating if we interrupt huey.
    script_directory = "update_scripts"
    scripts = find_shell_scripts(script_directory)
    error_msgs = []

    for script in scripts:
        with open(script, "r") as file:
            for line_number, line in enumerate(file, start=1):
                if line.lstrip().startswith("#"):  # comment
                    continue

                # Checking for 'systemctl restart huey'
                if "systemctl restart huey" in line:
                    error_msgs.append(
                        f"Error in {script} at line {line_number}: 'systemctl restart huey' should not be used since it will halt updates."
                    )

    assert not error_msgs, "\n".join(error_msgs)
