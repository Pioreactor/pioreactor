# -*- coding: utf-8 -*-
import sqlite3
from pathlib import Path

import pytest
from pioreactor.cli.status_checks import check_sqlite_storage
from pioreactor.cli.status_checks import ExpectedOwner
from pioreactor.cli.status_checks import StatusCheck
from pioreactor.cli.status_checks import worst_status
from pioreactor.config import config
from pioreactor.config import temporary_config_change

UNKNOWN_OWNER = ExpectedOwner(ids=None, description="pioreactor:www-data (missing on this system)")


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([], "OK"),
        (["OK", "OK"], "OK"),
        (["OK", "WARN", "OK"], "WARN"),
        (["WARN", "FAIL", "OK"], "FAIL"),
    ],
)
def test_worst_status_picks_most_severe(statuses: list, expected: str) -> None:
    checks = [StatusCheck(name=f"check{i}", status=s, details="") for i, s in enumerate(statuses)]
    assert worst_status(checks) == expected


def test_check_sqlite_storage_reports_openable_database_with_sidecars(tmp_path: Path) -> None:
    db_path = tmp_path / "pioreactor.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("create table t (x int);")
    Path(f"{db_path}-wal").write_bytes(b"x" * 2048)

    with temporary_config_change(config, "storage", "database", str(db_path)):
        check = check_sqlite_storage(
            "storage:db", "database", UNKNOWN_OWNER, check_openability=True, include_sidecars=True
        )

    assert check.status == "OK"
    assert check.details.startswith(f"{db_path} dir_writable=True db_size=")
    assert "wal_size=2.0KiB" in check.details
    assert "shm=missing" in check.details


def test_check_sqlite_storage_fails_when_database_to_open_is_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.sqlite"

    with temporary_config_change(config, "storage", "database", str(db_path)):
        check = check_sqlite_storage(
            "storage:db", "database", UNKNOWN_OWNER, check_openability=True, include_sidecars=False
        )

    assert check == StatusCheck(
        name="storage:db",
        status="FAIL",
        details=f"{db_path} dir_writable=True db=missing open_failed=missing",
    )


def test_check_sqlite_storage_warns_on_wrong_owner(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.sqlite"
    cache_path.write_bytes(b"")
    owner = ExpectedOwner(ids=(cache_path.stat().st_uid + 1, 0), description="pioreactor:www-data")

    with temporary_config_change(config, "storage", "temporary_cache", str(cache_path)):
        check = check_sqlite_storage(
            "storage:temporary_cache",
            "temporary_cache",
            owner,
            check_openability=False,
            include_sidecars=False,
        )

    assert check.status == "WARN"
    assert "dir_owner!= pioreactor:www-data" in check.details
    assert "db_owner!= pioreactor:www-data" in check.details
