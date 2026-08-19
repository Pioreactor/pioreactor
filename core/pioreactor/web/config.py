# -*- coding: utf-8 -*-
"""
this contains shared data for both huey and the flask app

"""
import sqlite3

from dotenv import load_dotenv
from huey.api import SqliteHuey
from pioreactor.paths import get_run_pioreactor_path


load_dotenv()

CACHE_DIR = get_run_pioreactor_path() / "cache"
CACHE_DIR.mkdir(exist_ok=True)

try:
    huey = SqliteHuey(filename=CACHE_DIR / "huey.db", fsync=False)
except sqlite3.OperationalError:
    raise IOError(f'Unable to open huey.db at {CACHE_DIR / "huey.db"}')
