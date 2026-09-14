# -*- coding: utf-8 -*-
import re
from pathlib import Path
from typing import Generator


SCRIPT_DIRECTORY = Path(__file__).resolve().parent.parent / "update_scripts" / "upcoming"
REQUIRED_BASH_SCRIPT_PREFIX = "#!/bin/bash\n\nset -xeu\n\nexport LC_ALL=C\n\n"
DESTRUCTIVE_SQL_PATTERNS = (
    re.compile(r"\bDROP\s+(?:TABLE|VIEW)\b", re.IGNORECASE),
    re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bPRAGMA\s+foreign_keys\s*=\s*OFF\b", re.IGNORECASE),
)


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

                commands_that_need_pioreactor_user_and_env = ["pio", "pios", "python"]

                for command in commands_that_need_pioreactor_user_and_env:
                    # Checking for 'pio', `pios` and `python` not preceded by 'sudo -u pioreactor -i'
                    if (f"{command} " in line or line.strip().startswith(f"{command} ")) and (
                        "sudo -u pioreactor -i" not in line
                    ):
                        error_msgs.append(
                            f"Error in {script} at line {line_number}: '{command}' command must be prefixed with 'sudo -u pioreactor -i'."
                        )

    assert not error_msgs, "\n".join(error_msgs)


def test_pios_commands_do_not_fail_for_offline_workers() -> None:
    error_msgs = []
    pios_command_pattern = re.compile(r"\bpios(?:\s|$)")

    for script in SCRIPT_DIRECTORY.rglob("*.sh"):
        for line_number, line in enumerate(script.read_text().splitlines(), start=1):
            if line.lstrip().startswith("#"):  # comment
                continue

            if pios_command_pattern.search(line) and not line.rstrip().endswith("|| :"):
                error_msgs.append(
                    f"Error in {script} at line {line_number}: 'pios' commands must end with '|| :' "
                    "so offline workers do not abort the update."
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


def test_crudini_uses_venv_binary() -> None:
    scripts = find_shell_scripts(SCRIPT_DIRECTORY)
    error_msgs = []
    crudini_pattern = re.compile(r"(^|[^-\w])(?:.*/)?crudini(\s|$)")

    for script in scripts:
        with open(script, "r") as file:
            for line_number, line in enumerate(file, start=1):
                if line.lstrip().startswith("#"):  # comment
                    continue

                if crudini_pattern.search(line) and "/opt/pioreactor/venv/bin/crudini" not in line:
                    error_msgs.append(
                        f"Error in {script} at line {line_number}: 'crudini' must be invoked via '/opt/pioreactor/venv/bin/crudini'."
                    )

    assert not error_msgs, "\n".join(error_msgs)


def test_update_bash_scripts_start_with_required_prefix() -> None:
    scripts = find_shell_scripts(SCRIPT_DIRECTORY)
    error_msgs = []

    for script in scripts:
        contents = script.read_text()
        if not contents.startswith(REQUIRED_BASH_SCRIPT_PREFIX):
            error_msgs.append(
                f"Error in {script}: update bash scripts must start with:\n{REQUIRED_BASH_SCRIPT_PREFIX!r}"
            )

    assert not error_msgs, "\n".join(error_msgs)


def test_destructive_sql_migrations_have_guardrails() -> None:
    error_msgs = []

    for script in find_sql_scripts(SCRIPT_DIRECTORY):
        contents = script.read_text()
        if not any(pattern.search(contents) for pattern in DESTRUCTIVE_SQL_PATTERNS):
            continue

        guardrails = {
            "BEGIN TRANSACTION": "wrap destructive changes in an explicit transaction",
            "COMMIT": "commit the explicit transaction",
            "PRAGMA foreign_keys = ON": "restore foreign-key enforcement",
            "PRAGMA foreign_key_check": "check for broken relationships after the rewrite",
        }
        for required_text, description in guardrails.items():
            if required_text not in contents:
                error_msgs.append(f"Error in {script}: destructive SQL migrations must {description}.")

    assert not error_msgs, "\n".join(error_msgs)


def test_raw_od_angle_migration(tmp_path: Path) -> None:
    import os
    import sqlite3
    import subprocess

    database = tmp_path / "test.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE raw_od_readings (od_reading REAL)")
        connection.execute("INSERT INTO raw_od_readings VALUES (0.25)")

    # Exercise the shipped shell script against SQLite without root or a real cluster.
    commands = {
        "sudo": '#!/bin/bash\nshift 3\nexec "$@"\n',
        "pio": '#!/bin/bash\nif [ "$3" = "storage" ]; then echo "$TEST_DATABASE"; else hostname; fi\n',
        "chown": "#!/bin/bash\nexit 0\n",
        "bash": '#!/bin/bash\ncase "$1" in */10_install_od_defaults.sh) exit 0;; esac\nexec /bin/bash "$@"\n',
    }
    for name, contents in commands.items():
        command = tmp_path / name
        command.write_text(contents)
        command.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "TEST_DATABASE": str(database)}
    for _ in range(2):
        subprocess.run(
            ["bash", str(SCRIPT_DIRECTORY / "update.sh")], env=env, check=True, capture_output=True
        )
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT od_reading, angle FROM raw_od_readings").fetchall() == [
                (0.25, None)
            ]
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO raw_od_readings VALUES (0.5, 0)")
    subprocess.run(["bash", str(SCRIPT_DIRECTORY / "update.sh")], env=env, check=True, capture_output=True)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT angle FROM raw_od_readings WHERE od_reading=0.5").fetchone() == (0,)


def test_od_defaults_preserve_existing_selection(tmp_path: Path) -> None:
    import os
    import subprocess
    from pioreactor.models import CORE_MODELS

    model_root = tmp_path / "models"
    probe = model_root / "pioreactor_40ml/1.5/od.yaml"
    probe.parent.mkdir(parents=True)
    probe.write_text("driver: turbidvision\nbus: 1\naddress: 0x69\n")
    install = tmp_path / "install"
    # Exercise real installation, omitting only ownership changes on the development host.
    install.write_text(
        '#!/bin/bash\nargs=()\nwhile [ "$#" -gt 0 ]; do\n'
        'case "$1" in -o|-g) shift 2;; *) args+=("$1"); shift;; esac\ndone\n'
        '/usr/bin/install "${args[@]}"\n'
    )
    install.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}
    seed_root = Path(__file__).resolve().parents[2] / "packaging/shared-assets/pioreactor/hardware/models"
    for _ in range(2):
        subprocess.run(
            ["bash", str(SCRIPT_DIRECTORY / "10_install_od_defaults.sh"), str(model_root)],
            env=env,
            check=True,
            capture_output=True,
        )
        for model in CORE_MODELS:
            relative = Path(model.model_name) / model.model_version / "od.yaml"
            assert (seed_root / relative).read_text() == "driver: photodiodes\n"
            installed = model_root / relative
            assert installed.read_text() == (
                "driver: turbidvision\nbus: 1\naddress: 0x69\n"
                if installed == probe
                else "driver: photodiodes\n"
            )
