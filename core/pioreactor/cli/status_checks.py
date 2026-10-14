# -*- coding: utf-8 -*-
"""
Local health checks behind `pio status`.

Each check returns a StatusCheck and reports its own failures in it, so one broken subsystem never stops
the rest of the report.
"""
import grp
import ipaddress
import os
import pwd
import shutil
import socket
import sqlite3
import stat
import subprocess
from contextlib import closing
from pathlib import Path
from typing import Literal

from msgspec import Struct
from pioreactor import exc
from pioreactor import hardware
from pioreactor import mureq
from pioreactor import pubsub
from pioreactor import whoami
from pioreactor.config import config
from pioreactor.paths import get_dot_pioreactor_path
from pioreactor.structs import Model
from pioreactor.utils import job_manager
from pioreactor.utils import networking
from pioreactor.version import get_firmware_version
from pioreactor.version import software_version_info
from pioreactor.version import tuple_to_text

CheckStatus = Literal["OK", "WARN", "FAIL"]

STATUS_SEVERITY: dict[CheckStatus, int] = {"OK": 0, "WARN": 1, "FAIL": 2}
MIN_FREE_DISK_GB = 3.0


class StatusCheck(Struct, frozen=True):
    name: str
    status: CheckStatus
    details: str


class ExpectedOwner(Struct, frozen=True):
    # (uid, gid), or None if the pioreactor user or www-data group is missing on this system.
    ids: tuple[int, int] | None
    description: str


def collect_status_checks() -> list[StatusCheck]:
    identity_check, role = check_identity()
    model_check, model = check_model()
    owner = get_expected_dot_pioreactor_owner()

    checks = [
        identity_check,
        model_check,
        check_hardware_model(model),
        check_version(),
        check_i2c_bus(),
        check_ipv4(),
        check_mqtt(),
        check_health_endpoint("services:web", "localhost"),
        check_leader_api(),
        check_huey_service(),
        check_running_jobs(),
        check_log_file(),
    ]

    if role == "leader":
        checks.append(
            check_sqlite_storage(
                "storage:db", "database", owner, check_openability=True, include_sidecars=True
            )
        )

    checks += [
        check_sqlite_storage(
            "storage:temporary_cache",
            "temporary_cache",
            owner,
            check_openability=False,
            include_sidecars=False,
        ),
        check_sqlite_storage(
            "storage:persistent_cache",
            "persistent_cache",
            owner,
            check_openability=False,
            include_sidecars=False,
        ),
        check_dot_pioreactor_tree(owner),
        check_disk_space(),
    ]
    return checks


def worst_status(checks: list[StatusCheck]) -> CheckStatus:
    return max((check.status for check in checks), key=STATUS_SEVERITY.__getitem__, default="OK")


def get_expected_dot_pioreactor_owner() -> ExpectedOwner:
    try:
        return ExpectedOwner(
            ids=(pwd.getpwnam("pioreactor").pw_uid, grp.getgrnam("www-data").gr_gid),
            description="pioreactor:www-data",
        )
    except KeyError:
        return ExpectedOwner(ids=None, description="pioreactor:www-data (missing on this system)")


def check_identity() -> tuple[StatusCheck, str]:
    """Also returns this unit's role, or "<unknown>" if it couldn't be determined."""
    unit = whoami.get_unit_name()
    role = "<unknown>"
    experiment = "<unknown>"
    problems: list[str] = []

    try:
        role = "leader" if whoami.am_I_leader() else "worker"
    except Exception as e:
        problems.append(f"role lookup failed ({e})")

    try:
        experiment = whoami.get_assigned_experiment_name(unit)
    except exc.NotAssignedAnExperimentError:
        experiment = ""
    except Exception as e:
        problems.append(f"experiment lookup failed ({e})")

    details = f"unit={unit} role={role} experiment={experiment}"
    if problems:
        return StatusCheck("identity", "WARN", f"{details} ({'; '.join(problems)})"), role
    return StatusCheck("identity", "OK", details), role


def check_model() -> tuple[StatusCheck, Model | None]:
    """Also returns this unit's model, or None if it couldn't be determined."""
    try:
        model = whoami.get_pioreactor_model()
    except exc.NoWorkerFoundError:
        return StatusCheck("model", "OK", "N/A"), None
    except (exc.NoModelAssignedError, exc.UnknownModelAssignedError) as e:
        return StatusCheck("model", "WARN", f"Unknown ({e})"), None
    except Exception as e:
        return StatusCheck("model", "WARN", f"lookup failed ({e})"), None
    return StatusCheck("model", "OK", model.display_name), model


def check_hardware_model(model: Model | None) -> StatusCheck:
    if model is None:
        return StatusCheck("hardware:model", "OK", "skipped: model unavailable")

    try:
        result = hardware.check_model_hardware_compatibility(model.model_name, model.model_version)
    except Exception as e:
        return StatusCheck("hardware:model", "WARN", f"lookup failed ({e})")

    if result["status"] == "warning":
        return StatusCheck("hardware:model", "WARN", result["reason"])
    elif result["status"] == "skipped":
        return StatusCheck("hardware:model", "OK", f"skipped: {result['reason']}")
    return StatusCheck("hardware:model", "OK", "compatible")


def check_version() -> StatusCheck:
    details = f"app={tuple_to_text(software_version_info)}"

    try:
        is_worker = whoami.am_I_a_worker()
    except Exception as e:
        return StatusCheck("version", "WARN", f"{details} worker=unknown ({e})")

    if not is_worker:
        return StatusCheck("version", "OK", details)

    try:
        firmware = tuple_to_text(get_firmware_version())
    except Exception:
        return StatusCheck("version", "WARN", f"{details} firmware=unknown")
    return StatusCheck("version", "OK", f"{details} firmware={firmware}")


def check_i2c_bus() -> StatusCheck:
    try:
        addresses = [f"0x{address:02x}" for address in hardware.scan_i2c_bus()]
    except Exception as e:
        return StatusCheck("hardware:i2c_bus1", "WARN", f"scan failed ({e})")
    return StatusCheck("hardware:i2c_bus1", "OK", ", ".join(addresses) or "none found")


def check_ipv4() -> StatusCheck:
    try:
        ipv4_addresses = networking.get_ip()
    except Exception as e:
        return StatusCheck("connectivity:ipv4", "FAIL", f"lookup failed ({e})")

    if not ipv4_addresses:
        return StatusCheck("connectivity:ipv4", "FAIL", "no IPv4 address found")

    try:
        for address in ipv4_addresses.split(","):
            ipaddress.IPv4Address(address)
    except ipaddress.AddressValueError:
        return StatusCheck("connectivity:ipv4", "FAIL", f"{ipv4_addresses} (invalid IPv4 address)")
    return StatusCheck("connectivity:ipv4", "OK", ipv4_addresses)


def check_mqtt() -> StatusCheck:
    broker_host, broker_port, config_note = "localhost", 1883, ""
    try:
        broker_host = config.get("mqtt", "broker_address", fallback="localhost").split(";")[0].strip()
        broker_port = config.getint("mqtt", "broker_port", fallback=1883)
    except Exception as e:
        config_note = f" (using defaults: {e})"

    try:
        with socket.create_connection((broker_host, broker_port), timeout=2):
            pass
    except Exception as e:
        return StatusCheck("connectivity:mqtt", "FAIL", f"{broker_host}:{broker_port} ({e}){config_note}")

    return StatusCheck(
        "connectivity:mqtt", "WARN" if config_note else "OK", f"{broker_host}:{broker_port}{config_note}"
    )


def check_health_endpoint(name: str, address: str) -> StatusCheck:
    url = "unit_api/health"
    try:
        url = pubsub.create_webserver_path(address, "unit_api/health")
        response = mureq.get(url, timeout=2)
    except Exception as e:
        return StatusCheck(name, "FAIL", f"{url} ({e})")

    if not response.ok:
        return StatusCheck(name, "FAIL", f"{url} (HTTP {response.status_code})")
    return StatusCheck(name, "OK", url)


def check_leader_api() -> StatusCheck:
    try:
        leader_address = config.get("cluster.topology", "leader_address", fallback="localhost")
    except Exception as e:
        return StatusCheck("connectivity:leader_api", "FAIL", f"unit_api/health ({e})")
    return check_health_endpoint("connectivity:leader_api", leader_address)


def check_huey_service() -> StatusCheck:
    systemctl_path = shutil.which("systemctl")
    if systemctl_path is None:
        return StatusCheck("services:huey", "WARN", "systemctl not available")

    # a non-zero return code is an answer here (ex: "inactive"), not a failure to run.
    result = subprocess.run(
        [systemctl_path, "is-active", "huey.service"],
        capture_output=True,
        text=True,
    )
    raw_status = (result.stdout or result.stderr).strip()
    is_active = result.returncode == 0 and raw_status == "active"
    return StatusCheck("services:huey", "OK" if is_active else "FAIL", raw_status or "unknown")


def check_running_jobs() -> StatusCheck:
    try:
        with job_manager.JobManager() as jm:
            running_jobs = jm.list_jobs()
    except Exception as e:
        return StatusCheck("jobs:running", "FAIL", str(e))
    return StatusCheck("jobs:running", "OK", f"count={len(running_jobs)}")


def check_log_file() -> StatusCheck:
    try:
        log_file = Path(config.get("logging", "log_file", fallback="/var/log/pioreactor.log"))
    except Exception:
        log_file = Path("/var/log/pioreactor.log")

    if not log_file.exists():
        return StatusCheck("storage:logs", "WARN", f"missing: {log_file}")
    return StatusCheck("storage:logs", "OK", str(log_file))


def check_sqlite_storage(
    name: str,
    config_key: str,
    owner: ExpectedOwner,
    *,
    check_openability: bool,
    include_sidecars: bool,
) -> StatusCheck:
    try:
        sqlite_path = Path(config.get("storage", config_key))
    except Exception as e:
        return StatusCheck(name, "WARN", f"storage.{config_key} missing ({e})")

    # status only escalates: storage problems are WARN, and only the openability check below can FAIL.
    status: CheckStatus = "OK"
    details = [str(sqlite_path)]

    storage_dir = sqlite_path.parent
    if storage_dir.exists():
        dir_writable = os.access(storage_dir, os.W_OK)
        details.append(f"dir_writable={dir_writable}")
        if not dir_writable:
            status = "WARN"
        if (problem := ownership_problem(storage_dir, "dir", owner)) is not None:
            status = "WARN"
            details.append(problem)
    else:
        status = "WARN"
        details.append("dir=missing")

    sqlite_files = {"db": sqlite_path}
    if include_sidecars:
        sqlite_files |= {"wal": Path(f"{sqlite_path}-wal"), "shm": Path(f"{sqlite_path}-shm")}

    for label, path in sqlite_files.items():
        if not path.exists():
            details.append(f"{label}=missing")
            if label == "db":
                status = "WARN"
            continue

        details.append(f"{label}_size={format_file_size(path)}")
        if (problem := ownership_problem(path, label, owner)) is not None:
            status = "WARN"
            details.append(problem)

    if check_openability and not sqlite_path.exists():
        status = "FAIL"
        details.append("open_failed=missing")
    elif check_openability:
        try:
            with closing(sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)) as conn:
                conn.execute("select 1;")
        except sqlite3.Error as e:
            status = "FAIL"
            details.append(f"open_failed={e}")

    return StatusCheck(name, status, " ".join(details))


def ownership_problem(path: Path, label: str, owner: ExpectedOwner) -> str | None:
    if owner.ids is None:
        return None

    try:
        stat_result = path.stat()
    except OSError as e:
        return f"{label}_stat_failed={e}"

    if (stat_result.st_uid, stat_result.st_gid) != owner.ids:
        return f"{label}_owner!= {owner.description}"
    return None


def format_file_size(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError as e:
        return f"unreadable({e})"

    if size < 1024:
        return f"{size}B"
    if size < 1024**2:
        return f"{size / 1024:.1f}KiB"
    if size < 1024**3:
        return f"{size / (1024**2):.1f}MiB"
    return f"{size / (1024**3):.1f}GiB"


def check_dot_pioreactor_tree(owner: ExpectedOwner) -> StatusCheck:
    root = get_dot_pioreactor_path()
    if not root.exists():
        return StatusCheck("storage:dot_pioreactor", "WARN", f"missing: {root}")

    paths = [root]
    for dirpath, dirnames, filenames in root.walk():
        paths.extend(dirpath / name for name in dirnames + filenames)

    status: CheckStatus = "OK"
    wrong_owner_count = 0
    missing_group_write_count = 0
    missing_setgid_dir_count = 0

    for path in paths:
        try:
            stat_result = path.lstat()
        except OSError:
            status = "WARN"
            continue

        if owner.ids is not None and (stat_result.st_uid, stat_result.st_gid) != owner.ids:
            wrong_owner_count += 1

        is_dir = stat.S_ISDIR(stat_result.st_mode)
        if (path == root or is_dir or stat.S_ISREG(stat_result.st_mode)) and not (
            stat_result.st_mode & stat.S_IWGRP
        ):
            missing_group_write_count += 1

        if is_dir and not stat_result.st_mode & stat.S_ISGID:
            missing_setgid_dir_count += 1

    if wrong_owner_count or missing_group_write_count or missing_setgid_dir_count:
        status = "WARN"

    details = (
        f"path={root} checked={len(paths)} "
        f"wrong_owner={wrong_owner_count} expected_owner={owner.description} "
        f"missing_group_write={missing_group_write_count} missing_setgid_dirs={missing_setgid_dir_count}"
    )
    return StatusCheck("storage:dot_pioreactor", status, details)


def check_disk_space() -> StatusCheck:
    try:
        free_gb = shutil.disk_usage("/").free / (1024**3)
    except OSError as e:
        return StatusCheck("storage:disk", "WARN", f"path=/ ({e})")
    return StatusCheck(
        "storage:disk", "WARN" if free_gb < MIN_FREE_DISK_GB else "OK", f"free={free_gb:.1f}GB path=/"
    )
