# -*- coding: utf-8 -*-
from __future__ import annotations

import click

from pioreactor.config import config
from pioreactor.config import get_active_workers_in_inventory
from pioreactor.logging import create_logger
from pioreactor.pubsub import subscribe
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import publish_ready_to_disconnected_state
from pioreactor.utils.networking import add_local
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT


def count_writes_occurring(unit: str) -> int:
    msg_or_none = subscribe(
        f"pioreactor/{unit}/{UNIVERSAL_EXPERIMENT}/mqtt_to_db_streaming/inserts_in_last_60s",
        timeout=2,
    )
    if msg_or_none is not None:
        count = int(msg_or_none.payload.decode())
    else:
        count = 0
    return count


def backup_database(output_file: str, force: bool = False) -> None:
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
    from sh import ErrorReturnCode, rsync  # type: ignore

    unit = get_unit_name()
    experiment = UNIVERSAL_EXPERIMENT

    with publish_ready_to_disconnected_state(unit, experiment, "backup_database"):
        logger = create_logger(
            "backup_database", experiment=experiment, unit=unit, to_mqtt=False
        )  # the backup would take so long that the mqtt client would disconnect. We also don't want to write to the db.

        logger.debug(f"Starting backup of database to {output_file}")

        if not force and count_writes_occurring(unit) >= 2:
            logger.debug("Too many writes to proceed with backup. Exiting.")
            return

        current_time = current_utc_timestamp()
        page_size = 50

        con = sqlite3.connect(config.get("storage", "database"))
        bck = sqlite3.connect(output_file)

        with bck:
            # why 50? A larger sqlite3 database we used had 164510 pages.
            # pages=5 took 4m
            # pages=50 took 2m
            # we don't want it too big though, else it locks up the database for too long. We had problems with pages=-1
            con.backup(bck, pages=page_size)

        bck.close()
        con.close()

        with local_persistant_storage("database_backups") as cache:
            cache["latest_backup_timestamp"] = current_time

        logger.info("Completed backup of database.")

        # back up to workers, if available
        n_backups = config.getint("storage", "number_of_backup_replicates_to_workers", fallback=0)
        backups_complete = 0
        available_workers = list(get_active_workers_in_inventory())

        while (backups_complete < n_backups) and (len(available_workers) > 0):
            backup_unit = available_workers.pop()
            if backup_unit == unit:
                continue

            logger.debug(f"Attempting backing up database to {backup_unit}.")
            try:
                rsync(
                    "-hz",
                    "--partial",
                    "--inplace",
                    output_file,
                    f"{add_local(backup_unit)}:{output_file}",
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

                with local_persistant_storage("database_backups") as cache:
                    cache[f"latest_backup_in_{backup_unit}"] = current_time

        return


@click.command(name="backup_database")
@click.option("--output", default="/home/pioreactor/.pioreactor/storage/pioreactor.sqlite.backup")
@click.option("--force", is_flag=True, help="force backing up")
def click_backup_database(output: str, force: bool) -> None:
    """
    (leader only) Backup db to workers.
    """
    return backup_database(output, force)
