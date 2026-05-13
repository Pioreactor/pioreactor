# -*- coding: utf-8 -*-
import sqlite3
from pathlib import Path

from pioreactor.config import config as pioreactor_config


def get_app_database_path() -> Path:
    return Path(pioreactor_config.get("storage", "database"))


def open_app_database_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_app_database_path())
    conn.executescript(
        """
        PRAGMA synchronous = 1;
        PRAGMA temp_store = 2;
        PRAGMA busy_timeout = 15000;
        PRAGMA foreign_keys = ON;
        PRAGMA recursive_triggers = ON;
        PRAGMA cache_size = -4000;
    """
    )
    return conn


def get_database_space_stats(conn: sqlite3.Connection) -> dict[str, int | float]:
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
    freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
    reclaimable_bytes = page_size * freelist_count
    allocated_bytes = page_size * page_count
    reclaimable_fraction = (freelist_count / page_count) if page_count else 0.0

    return {
        "page_size": page_size,
        "page_count": page_count,
        "freelist_count": freelist_count,
        "allocated_bytes": allocated_bytes,
        "reclaimable_bytes": reclaimable_bytes,
        "reclaimable_fraction": reclaimable_fraction,
    }
