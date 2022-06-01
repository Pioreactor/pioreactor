# -*- coding: utf-8 -*-
from __future__ import annotations

from time import sleep

import click

from pioreactor.config import config
from pioreactor.config import get_active_workers_in_inventory
from pioreactor.logging import create_logger
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def backup_database(output_file: str) -> None:
    """
    This action will create a backup of the SQLite3 database into specified output. It then
    will try to copy the backup to any available worker Pioreactors as a further backup.

    This job actually consumes _a lot_ of resources, and I've seen the LED output
    drop due to this running. See issue #81. For now, we will skip the backup if `od_reading` is running

    Elsewhere, a cronjob is set up as well to run this action every N days.

    TODO: we should gzip before sending it, "B-tree databases like SQLite compress well so it’s recommended to compress your database"
    """

    import sqlite3
    from sh import ErrorReturnCode, rsync  # type: ignore

    unit = get_unit_name()
    experiment = UNIVERSAL_EXPERIMENT

    with publish_ready_to_disconnected_state(unit, experiment, "backup_database"):

        logger = create_logger("backup_database", experiment=experiment, unit=unit)

        if is_pio_job_running("od_reading"):
            logger.warning("Won't run if OD Reading is running. Exiting")
            return

        def progress(status: int, remaining: int, total: int) -> None:
            logger.debug(f"Copied {total-remaining} of {total} SQLite3 pages.")
            logger.debug(f"Writing to local backup {output_file}.")

        logger.debug(f"Starting backup of database to {output_file}")
        sleep(1)  # pause a second so the log entry above gets recorded into the DB.

        con = sqlite3.connect(config.get("storage", "database"))
        bck = sqlite3.connect(output_file)

        with bck:
            con.backup(bck, pages=-1, progress=progress)

        bck.close()
        con.close()

        with local_persistant_storage("database_backups") as cache:
            cache["latest_backup_timestamp"] = current_utc_timestamp()

        logger.info("Completed backup of database.")

        n_backups = config.getint("storage", "number_of_backup_replicates_to_workers", fallback=0)
        backups_complete = 0
        available_workers = list(get_active_workers_in_inventory())

        while (backups_complete < n_backups) and (len(available_workers) > 0):
            backup_unit = available_workers.pop()
            if backup_unit == get_unit_name():
                continue

            try:
                rsync(
                    "-hz",
                    "--partial",
                    "--inplace",
                    output_file,
                    f"{backup_unit}:{output_file}",
                )
            except ErrorReturnCode:
                logger.debug(
                    f"Unable to backup database to {backup_unit}. Is it online?",
                    exc_info=True,
                )
                logger.warning(f"Unable to backup database to {backup_unit}. Is it online?")
            else:
                logger.debug(f"Backed up database to {backup_unit}:{output_file}.")
                backups_complete += 1

        return


@click.command(name="backup_database")
@click.option("--output", default="/home/pioreactor/.pioreactor/storage/pioreactor.sqlite.backup")
def click_backup_database(output: str) -> None:
    """
    (leader only) Backup db to workers.
    """
    return backup_database(output)
