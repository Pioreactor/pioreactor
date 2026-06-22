# -*- coding: utf-8 -*-
# Copyright (c) 2014 Palantir Technologies, 2020s Pioreactor
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
"""Thread safe sqlite3 interface."""
import sqlite3
import threading
from queue import Empty
from queue import Queue
from time import monotonic
from typing import Any
from typing import Callable

type SqliteValues = tuple[Any, ...] | dict[str, Any]
type SqliteErrorCallback = Callable[[Exception, str, SqliteValues], None]


class Sqlite3Worker(threading.Thread):
    """Sqlite thread safe object.

    Example:
        from sqlite3worker import Sqlite3Worker
        sql_worker = Sqlite3Worker("/tmp/test.sqlite")
        sql_worker.execute(
            "CREATE TABLE tester (timestamp DATETIME, uuid TEXT)")
        sql_worker.execute(
            "INSERT into tester values (?, ?)", ("2010-01-01 13:00:00", "bow"))
        sql_worker.execute(
            "INSERT into tester values (?, ?)", ("2011-02-02 14:14:14", "dog"))
        sql_worker.close()
    """

    def __init__(
        self,
        file_name: str,
        max_queue_size: int = 100,
        max_batch_delay_s: float | None = None,
        raise_on_error: bool = True,
        on_error: SqliteErrorCallback | None = None,
    ) -> None:
        """Automatically starts the thread.

        Args:
            file_name: The name of the file.
            max_queue_size: The max queries that will be queued.
            max_batch_delay_s: The max time to wait before committing queued writes.
            raise_on_error: raise the exception on commit error
            on_error: Called when a queued write or commit fails.
        """
        threading.Thread.__init__(self, name=__name__)
        self.daemon = True
        self._sqlite3_conn = sqlite3.connect(
            file_name, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES
        )
        self._sqlite3_cursor = self._sqlite3_conn.cursor()
        self._sqlite3_cursor.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous = NORMAL;
            PRAGMA temp_store = MEMORY;
            PRAGMA busy_timeout = 15000;
            PRAGMA foreign_keys = ON;
            PRAGMA recursive_triggers = ON;
            PRAGMA cache_size = -4000;

            PRAGMA wal_autocheckpoint = 4000;
            PRAGMA mmap_size = 268435456;
        """
        )
        self._sql_queue: Queue[tuple[str, SqliteValues]] = Queue(maxsize=max_queue_size)
        self._max_queue_size = max_queue_size
        self._max_batch_delay_s = max_batch_delay_s
        self._raise_on_error = raise_on_error
        self._on_error = on_error
        # Event to start the close process.
        self._close_event = threading.Event()
        # Event that closes out the threads.
        self._close_lock = threading.Lock()
        self.start()

    def run(self) -> None:
        """Thread loop.

        This is an infinite loop.  The iter method calls self._sql_queue.get()
        which blocks if there are not values in the queue.  As soon as values
        are placed into the queue the process will continue.

        If many executes happen at once it will churn through them all before
        calling commit() to speed things up by reducing the number of times
        commit is called.
        """

        execute_count = 0
        batch_deadline: float | None = None

        while True:
            if self._max_batch_delay_s is not None and batch_deadline is not None:
                timeout = max(0, batch_deadline - monotonic())
            else:
                timeout = None

            try:
                query, values = self._sql_queue.get(timeout=timeout)
            except Empty:
                if execute_count:
                    self.commit_pending_writes()
                    execute_count = 0
                batch_deadline = None
                continue

            if query:
                self.run_query(query, values)
                execute_count += 1
                if batch_deadline is None and self._max_batch_delay_s is not None:
                    batch_deadline = monotonic() + self._max_batch_delay_s

                if self._max_batch_delay_s is None and self._sql_queue.empty():
                    self.commit_pending_writes()
                    execute_count = 0
                    batch_deadline = None
                elif execute_count == self._max_queue_size:
                    self.commit_pending_writes()
                    execute_count = 0
                    batch_deadline = None
                elif batch_deadline is not None and monotonic() >= batch_deadline:
                    self.commit_pending_writes()
                    execute_count = 0
                    batch_deadline = None

            if self._close_event.is_set() and self._sql_queue.empty():
                if execute_count:
                    self.commit_pending_writes()
                self._sqlite3_conn.close()
                return

    def report_error(self, error: Exception, query: str, values: SqliteValues) -> None:
        if self._on_error is not None:
            self._on_error(error, query, values)

    def commit_pending_writes(self) -> None:
        try:
            self._sqlite3_conn.commit()
        except Exception as e:
            self.report_error(e, "COMMIT", tuple())
            if self._raise_on_error:
                raise e

    def run_query(self, query: str, values: SqliteValues) -> None:
        """Run a query.

        Args:
            query: A sql query with ? placeholders for values.
            values: A tuple of values to replace "?" in query.
        """
        try:
            self._sqlite3_cursor.execute(query, values)
        except sqlite3.Error as e:
            self.report_error(e, query, values)
            if self._raise_on_error:
                raise e

    def close(self) -> None:
        """Close down the thread."""
        with self._close_lock:
            if not self.is_alive():
                return
            self._close_event.set()
            # Put a value in the queue to push through the block waiting for
            # items in the queue.
            self._sql_queue.put(("", ("",)), timeout=5)
            # Check that the thread is done before returning.
            self.join()

    def execute(self, query: str, values: SqliteValues | None = None) -> str | None:
        """Execute a query.

        Args:
            query: The sql string using ? for placeholders of dynamic values.
            values: A tuple of values to be replaced into the ? of the query.
        """
        if self._close_event.is_set():
            return "Close Called"

        if query.lower().strip().startswith("select"):
            raise ValueError(
                "Sqlite3Worker is write-only. Use a SQLite connection directly for SELECT queries."
            )

        values = values or tuple()
        self._sql_queue.put((query, values), timeout=5)
        return None
