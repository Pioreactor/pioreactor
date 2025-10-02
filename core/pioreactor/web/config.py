# -*- coding: utf-8 -*-
"""
this contains shared data for both huey and the flask app

"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from huey import SqliteHuey


load_dotenv()

CACHE_DIR = Path(os.environ["RUN_PIOREACTOR"]) / "cache"

try:
    huey = SqliteHuey(filename=CACHE_DIR / "huey.db")
except sqlite3.OperationalError:
    raise IOError(f'Unable to open huey.db at {CACHE_DIR / "huey.db"}')
