# -*- coding: utf-8 -*-
import sqlite3
from contextlib import contextmanager
from typing import Generator
from typing import Self

from msgspec import DecodeError
from msgspec.json import decode as loads
from msgspec.json import encode as dumps
from pioreactor.config import config

_MISSING = object()


def _restore_tuple_keys(value: object) -> object:
    if isinstance(value, list):
        return tuple(_restore_tuple_keys(item) for item in value)
    return value


def _to_float(value: object) -> float:
    if isinstance(value, bytes):
        return float(value.decode())
    if isinstance(value, (float, int, str)):
        return float(value)
    raise TypeError(f"Cannot interpret {value!r} as float.")


def _to_int(value: object) -> int:
    if isinstance(value, bytes):
        return int(value.decode())
    if isinstance(value, (float, int, str)):
        return int(value)
    raise TypeError(f"Cannot interpret {value!r} as int.")


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, bytes):
        value = value.decode()
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "yes", "true", "on"}:
            return True
        if normalized in {"0", "no", "false", "off"}:
            return False
        raise ValueError(f"Cannot interpret {value!r} as bool.")
    return bool(value)


def _decode_json(value: object) -> object:
    if isinstance(value, (bytes, str, bytearray)):
        return loads(value)
    raise TypeError(f"Cannot interpret {value!r} as JSON.")


class cache:
    @staticmethod
    def adapt_key(key: object) -> bytes:
        # keys can be tuples!
        return dumps(key)

    @staticmethod
    def convert_key(s: str | bytes) -> object:
        if isinstance(s, bytes):
            try:
                return _restore_tuple_keys(loads(s))
            except DecodeError:
                return s.decode()
        return s

    def __init__(self, table_name: str, db_path: str) -> None:
        self.table_name = f"cache_{table_name}"
        self.db_path = db_path

    def __enter__(self) -> Self:
        sqlite3.register_adapter(tuple, self.adapt_key)
        # sqlite3.register_converter("_key_BLOB", self.convert_key)

        self.conn = sqlite3.connect(
            self.db_path, detect_types=sqlite3.PARSE_DECLTYPES, isolation_level=None, timeout=10
        )
        self.cursor = self.conn.cursor()
        self.cursor.executescript(
            """
            PRAGMA busy_timeout = 5000;
            PRAGMA temp_store = 2;
            PRAGMA cache_size = -4000;
        """
        )
        self._initialize_table()
        return self

    def __exit__(self, exc_type: object, exc_val: object, tb: object) -> None:
        self.conn.close()

    def _initialize_table(self) -> None:
        self.cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                key _key_BLOB PRIMARY KEY,
                value BLOB
            )
        """
        )

    def __setitem__(self, key: object, value: object) -> None:
        self.cursor.execute(
            f"""
            INSERT INTO {self.table_name} (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
            (key, value),
        )

    def set(self, key: object, value: object) -> None:
        return self.__setitem__(key, value)

    def set_if_absent(self, key: object, value: object) -> bool:
        self.cursor.execute(
            f"""
            INSERT OR IGNORE INTO {self.table_name} (key, value)
            VALUES (?, ?)
        """,
            (key, value),
        )
        return self.cursor.rowcount == 1

    def get(self, key: object, default: object = None) -> object:
        self.cursor.execute(f"SELECT value FROM {self.table_name} WHERE key = ?", (key,))
        result = self.cursor.fetchone()
        return result[0] if result else default

    def getfloat(self, key: object, *, fallback: float | object = _MISSING) -> float:
        value = self.get(key, _MISSING)
        if value is _MISSING:
            if fallback is _MISSING:
                raise KeyError(f"Key '{key}' not found in cache.")
            return _to_float(fallback)
        return _to_float(value)

    def getint(self, key: object, *, fallback: int | object = _MISSING) -> int:
        value = self.get(key, _MISSING)
        if value is _MISSING:
            if fallback is _MISSING:
                raise KeyError(f"Key '{key}' not found in cache.")
            return _to_int(fallback)
        return _to_int(value)

    def getboolean(self, key: object, *, fallback: bool | object = _MISSING) -> bool:
        value = self.get(key, _MISSING)
        if value is _MISSING:
            if fallback is _MISSING:
                raise KeyError(f"Key '{key}' not found in cache.")
            return _to_bool(fallback)
        return _to_bool(value)

    def getjson(self, key: object, default: object = None) -> object:
        value = self.get(key, default)
        if value is default:
            return default
        return _decode_json(value)

    def iterkeys(self) -> Generator[object, None, None]:
        self.cursor.execute(f"SELECT key FROM {self.table_name}")
        return (self.convert_key(row[0]) for row in self.cursor.fetchall())

    def pop(self, key: object, default: object = None) -> object:
        self.cursor.execute(f"DELETE FROM {self.table_name} WHERE key = ? RETURNING value", (key,))
        result = self.cursor.fetchone()

        if result is None:
            return default
        else:
            return result[0]

    def empty(self) -> None:
        self.cursor.execute(f"DELETE FROM {self.table_name}")

    def __contains__(self, key: object) -> bool:
        self.cursor.execute(f"SELECT 1 FROM {self.table_name} WHERE key = ?", (key,))
        return self.cursor.fetchone() is not None

    def __iter__(self) -> Generator[object, None, None]:
        return self.iterkeys()

    def __delitem__(self, key: object) -> None:
        self.cursor.execute(f"DELETE FROM {self.table_name} WHERE key = ?", (key,))

    def __getitem__(self, key: object) -> object:
        self.cursor.execute(f"SELECT value FROM {self.table_name} WHERE key = ?", (key,))
        result = self.cursor.fetchone()
        if result is None:
            raise KeyError(f"Key '{key}' not found in cache.")
        return result[0]


@contextmanager
def local_intermittent_storage(
    cache_name: str,
) -> Generator[cache, None, None]:
    """

    The cache is deleted upon a Raspberry Pi restart!

    Examples
    ---------
    > with local_intermittent_storage('pwm') as cache:
    >     assert '1' in cache
    >     cache['1'] = 0.5


    Notes
    -------
    Opening the same cache in a context manager is tricky, and should be avoided.

    """
    with cache(cache_name, db_path=config.get("storage", "temporary_cache")) as c:
        yield c


@contextmanager
def local_persistent_storage(
    cache_name: str,
) -> Generator[cache, None, None]:
    """
    Values stored in this storage will stay around between RPi restarts, and until overwritten
    or deleted.

    Examples
    ---------
    > with local_persistent_storage('od_blank') as cache:
    >     assert '1' in cache
    >     cache['1'] = 0.5

    """

    with cache(cache_name, db_path=config.get("storage", "persistent_cache")) as c:
        yield c
