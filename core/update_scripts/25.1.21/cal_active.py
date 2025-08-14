# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3

import click
from pioreactor.utils import local_persistent_storage


def old_active_calibrations(sql_database: str):
    try:
        conn = sqlite3.connect(sql_database)
    except sqlite3.OperationalError:
        return
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM cache")

    for row in cursor.fetchall():
        data = json.loads(row[0])
        yield data


@click.command()
@click.argument("db_location")
def main(db_location: str) -> None:
    with local_persistent_storage("active_calibrations") as c:
        for old_cal in old_active_calibrations(db_location):
            if "pump" in old_cal["type"]:
                type_ = old_cal["type"]
            elif "od" in old_cal["type"]:
                type_ = "od"
            else:
                print(f"Unknown type {old_cal['type']}")
                continue

            c[type_] = old_cal["name"]
            print(f"Setting active calibration for {type_} to {old_cal['name']}")


if __name__ == "__main__":
    main()
