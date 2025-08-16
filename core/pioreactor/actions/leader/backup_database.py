# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import click
from pioreactor.cluster_management import get_active_workers_in_inventory
from pioreactor.config import config
from pioreactor.exc import RsyncError
from pioreactor.logging import create_logger
from pioreactor.mureq import HTTPException
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistent_storage
from pioreactor.utils import long_running_managed_lifecycle
from pioreactor.utils.networking import resolve_to_address
from pioreactor.utils.networking import rsync
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def _remote_available_space(address: str, path: str) -> int | None:
    """Return available bytes on remote machine or ``None`` on failure."""
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", address, "df", "-PB1", path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError:
        return None

    try:
        lines = result.stdout.strip().splitlines()
        if len(lines) >= 2:
            return int(lines[1].split()[3])
    except Exception:
        return None

    return None


def _local_available_space(path: str) -> int:
    """Return available bytes on the local filesystem."""
    statvfs = os.statvfs(path)
    return statvfs.f_frsize * statvfs.f_bavail


def count_writes_occurring() -> int:
    with local_intermittent_storage("mqtt_to_db_streaming") as c:
        return c.get("inserts_in_last_60s", 0)


def backup_database(output_file: str, force: bool = False, backup_to_workers: int = 0) -> None:
    """
    This action will create a backup of the SQLite3 database into specified output. It then
    will try to copy the backup to any available worker Pioreactors as a further backup.

    This job actually consumes _a lot_ of resources, and I've seen the LED output
    drop due to this running. See issue #81.

    To avoid database corruption, and to dodge when activities are happening, we will skip the backup if there are too many writes occurring

    Elsewhere, a cronjob is set up as well to run this action every N days.

    TODO: backup more historical copies, too. Like a versioning system that logrotate does.
    """

    import sqlite3

    unit = get_unit_name()
    experiment = UNIVERSAL_EXPERIMENT

    with long_running_managed_lifecycle(unit, experiment, "backup_database") as mj:
        logger = create_logger(
            mj.job_key, experiment=experiment, unit=unit, to_mqtt=False
        )  # the backup would take so long that the mqtt client would disconnect. We also don't want to write to the db.

        logger.debug(f"Starting backup of database to {output_file}")

        db_path = config.get("storage", "database")
        db_size = Path(db_path).stat().st_size

        available = _local_available_space(str(Path(output_file).parent))
        margin = 1.1
        if available < db_size * margin:
            logger.debug("Skipping backup. Not enough disk space on local machine.")
            logger.warning("Unable to backup database locally. Not enough disk space.")
            return

        if not force and count_writes_occurring() >= 10:
            logger.debug("Too many writes to proceed with backup. Exiting. Use --force to force backing up.")
            return

        current_time = current_utc_timestamp()
        page_size = 50

        con = sqlite3.connect(f"file:{config.get('storage', 'database')}?mode=ro", uri=True)
        bck = sqlite3.connect(output_file)

        with bck:
            # why 50? A larger sqlite3 database we used had 164510 pages.
            # pages=5 took 4m
            # pages=50 took 2m
            # we don't want it too big though, else it locks up the database for too long. We had problems with pages=-1
            con.backup(bck, pages=page_size)

        bck.close()
        con.close()

        with local_persistent_storage("database_backups") as cache:
            cache["latest_backup_timestamp"] = current_time

        logger.info("Completed backup of database.")

        # back up to workers, if available
        backups_complete = 0
        try:
            available_workers = list(get_active_workers_in_inventory())
        except HTTPException:
            # server is offline, sometimes happens during a full export
            available_workers = []

        while (backups_complete < backup_to_workers) and (len(available_workers) > 0):
            backup_unit = available_workers.pop()
            if backup_unit == unit:
                continue

            logger.debug(f"Attempting backing up database to {backup_unit}.")
            available_on_remote = _remote_available_space(
                resolve_to_address(backup_unit), str(Path(output_file).parent)
            )
            if available_on_remote is not None and available_on_remote < Path(output_file).stat().st_size:
                logger.debug(f"Skipping backup to {backup_unit}. Not enough disk space.")
                logger.warning(f"Unable to backup database to {backup_unit}. Not enough disk space.")
                continue
            try:
                rsync(
                    "-hz",
                    "--partial",
                    "--inplace",
                    output_file,
                    f"{resolve_to_address(backup_unit)}:{output_file}",
                )
            except RsyncError:
                logger.debug(
                    f"Unable to backup database to {backup_unit}. Is it online?",
                    exc_info=True,
                )
                logger.warning(f"Unable to backup database to {backup_unit}. Is it online?")
            else:
                logger.debug(f"Backed up database to {backup_unit}:{output_file}.")
                backups_complete += 1

                with local_persistent_storage("database_backups") as cache:
                    cache[f"latest_backup_in_{backup_unit}_timestamp"] = current_time

        return


@click.command(name="backup_database")
@click.option("--output", default="/home/pioreactor/.pioreactor/storage/pioreactor.sqlite.backup")
@click.option("--force", is_flag=True, help="force backing up")
@click.option("--backup-to-workers", help="back up db to N workers", type=int)
def click_backup_database(output: str, force: bool, backup_to_workers: int | None) -> None:
    """
    (leader only) Backup db to workers.
    """
    number_of_backup_replicates_to_workers = (
        backup_to_workers
        if backup_to_workers is not None
        else config.getint("storage", "number_of_backup_replicates_to_workers", fallback=0)
    )

    return backup_database(output, force, number_of_backup_replicates_to_workers)
