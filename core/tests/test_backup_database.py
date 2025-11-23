# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

from pioreactor.actions.leader.backup_database import backup_database
from pioreactor.config import config
from pioreactor.config import temporary_config_change


@contextmanager
def dummy_lifecycle(*args, **kwargs):
    yield SimpleNamespace(job_key="backup_database")


def test_skip_backup_when_worker_has_no_space(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite"

    with temporary_config_change(config, "storage", "database", str(db_path)):
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t(id INTEGER)")
        conn.commit()
        conn.close()

        output = tmp_path / "backup.sqlite"

        with (
            patch(
                "pioreactor.actions.leader.backup_database.long_running_managed_lifecycle",
                dummy_lifecycle,
            ),
            patch(
                "pioreactor.actions.leader.backup_database.create_logger",
                return_value=MagicMock(),
            ),
            patch(
                "pioreactor.actions.leader.backup_database.get_active_workers_in_inventory",
                return_value=["worker1"],
            ),
            patch(
                "pioreactor.actions.leader.backup_database._remote_available_space",
                return_value=0,
            ),
            patch(
                "pioreactor.actions.leader.backup_database.rsync",
            ) as mock_rsync,
        ):
            backup_database(str(output), force=True, backup_to_workers=1)
            mock_rsync.assert_not_called()


def test_skip_backup_when_local_has_no_space(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite"

    with temporary_config_change(config, "storage", "database", str(db_path)):
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t(id INTEGER)")
        conn.commit()
        conn.close()

        output = tmp_path / "backup.sqlite"

        with (
            patch(
                "pioreactor.actions.leader.backup_database.long_running_managed_lifecycle",
                dummy_lifecycle,
            ),
            patch(
                "pioreactor.actions.leader.backup_database.create_logger",
                return_value=MagicMock(),
            ),
            patch(
                "pioreactor.actions.leader.backup_database._local_available_space",
                return_value=0,
            ),
            patch(
                "sqlite3.connect",
            ) as mock_connect,
        ):
            backup_database(str(output), force=True, backup_to_workers=0)
            mock_connect.assert_not_called()
