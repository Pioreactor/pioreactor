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
from __future__ import annotations

import queue as Queue
import sqlite3
import threading
import uuid
from typing import Optional


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
        sql_worker.execute("SELECT * from tester")
        sql_worker.close()
    """

    def __init__(self, file_name, max_queue_size=100, raise_on_error=True):
        """Automatically starts the thread.

        Args:
            file_name: The name of the file.
            max_queue_size: The max queries that will be queued.
            raise_on_error: raise the exception on commit error
        """
        threading.Thread.__init__(self, name=__name__)
        self.daemon = True
        self._sqlite3_conn = sqlite3.connect(
            file_name, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES
        )
        self._sqlite3_cursor = self._sqlite3_conn.cursor()
        self._sql_queue = Queue.Queue(maxsize=max_queue_size)
        self._results = {}
        self._max_queue_size = max_queue_size
        self._raise_on_error = raise_on_error
        # Event that is triggered once the run_query has been executed.
        self._select_events = {}
        # Event to start the close process.
        self._close_event = threading.Event()
        # Event that closes out the threads.
        self._close_lock = threading.Lock()
        self.start()

    def run(self):
        """Thread loop.

        This is an infinite loop.  The iter method calls self._sql_queue.get()
        which blocks if there are not values in the queue.  As soon as values
        are placed into the queue the process will continue.

        If many executes happen at once it will churn through them all before
        calling commit() to speed things up by reducing the number of times
        commit is called.
        """

        execute_count = 0
        for token, query, values in iter(self._sql_queue.get, None):
            if query:
                self._run_query(token, query, values)
                execute_count += 1
                # Let the executes build up a little before committing to disk
                # to speed things up and reduce the number of writes to disk.
                if self._sql_queue.empty() or execute_count == self._max_queue_size:
                    try:
                        self._sqlite3_conn.commit()
                        execute_count = 0
                    except Exception as e:
                        if self._raise_on_error:
                            raise e
            # Only close if the queue is empty.  Otherwise keep getting
            # through the queue until it's empty.
            if self._close_event.is_set() and self._sql_queue.empty():
                self._sqlite3_conn.commit()
                self._sqlite3_conn.close()
                return

    def _run_query(self, token: str, query: str, values: tuple):
        """Run a query.

        Args:
            token: A uuid object of the query you want returned.
            query: A sql query with ? placeholders for values.
            values: A tuple of values to replace "?" in query.
        """
        if query.lower().strip().startswith("select"):
            try:
                self._sqlite3_cursor.execute(query, values)
                self._results[token] = self._sqlite3_cursor.fetchall()
            except sqlite3.Error as err:
                # Put the error into the output queue since a response
                # is required.
                self._results[token] = "Query returned error: %s: %s: %s" % (
                    query,
                    values,
                    err,
                )

            finally:
                # Wake up the thread waiting on the execution of the select
                # query.
                self._select_events.setdefault(token, threading.Event())
                self._select_events[token].set()
        else:
            try:
                self._sqlite3_cursor.execute(query, values)
            except sqlite3.Error:
                pass

    def close(self):
        """Close down the thread."""
        with self._close_lock:
            if not self.is_alive():
                return "Already Closed"
            self._close_event.set()
            # Put a value in the queue to push through the block waiting for
            # items in the queue.
            self._sql_queue.put(("", "", ""), timeout=5)
            # Check that the thread is done before returning.
            self.join()

    @property
    def queue_size(self):
        """Return the queue size."""
        return self._sql_queue.qsize()

    def _query_results(self, token: str):
        """Get the query results for a specific token.

        Args:
            token: A uuid object of the query you want returned.

        Returns:
            Return the results of the query when it's executed by the thread.
        """
        try:
            # Wait until the select query has executed
            self._select_events.setdefault(token, threading.Event())
            self._select_events[token].wait()
            return self._results[token]
        finally:
            self._select_events[token].clear()
            del self._results[token]
            del self._select_events[token]

    def execute(self, query: str, values: Optional[list] = None):
        """Execute a query.

        Args:
            query: The sql string using ? for placeholders of dynamic values.
            values: A tuple of values to be replaced into the ? of the query.

        Returns:
            If it's a select query it will return the results of the query.
        """
        if self._close_event.is_set():
            return "Close Called"

        values = values or []
        # A token to track this query with.
        token = str(uuid.uuid4())
        self._sql_queue.put((token, query, values), timeout=5)
        # If it's a select we queue it up with a token to mark the results
        # into the output queue so we know what results are ours.
        if query.lower().strip().startswith("select"):
            return self._query_results(token)
