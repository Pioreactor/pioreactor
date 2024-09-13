# -*- coding: utf-8 -*-
from __future__ import annotations

import os


def find_shell_scripts(directory):
    """Recursively find all shell script files in the specified directory."""
    types = {"update.sh", "pre_update.sh", "post_update.sh"}
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file in types:
                yield os.path.join(root, file)


def test_pio_commands():
    script_directory = "update_scripts"
    scripts = find_shell_scripts(script_directory)
    error_msgs = []

    for script in scripts:
        with open(script, "r") as file:
            for line_number, line in enumerate(file, start=1):
                if line.lstrip().startswith("#"):  # comment
                    continue

                # Checking for 'pio' not preceded by 'su -u pioreactor'
                if (" pio " in line or line.strip().startswith("pio")) and "sudo -u pioreactor" not in line:
                    error_msgs.append(
                        f"Error in {script} at line {line_number}: 'pio' command must be prefixed with 'su -u pioreactor'."
                    )

    assert not error_msgs, "\n".join(error_msgs)
