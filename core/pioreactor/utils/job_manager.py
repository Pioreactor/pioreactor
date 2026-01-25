# -*- coding: utf-8 -*-
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from subprocess import run
from typing import Any

from msgspec import Struct
from msgspec.json import encode as dumps
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.config import config
from pioreactor.exc import JobRequiredError
from pioreactor.exc import RoleError
from pioreactor.pubsub import patch_into
from pioreactor.utils.networking import resolve_to_address
from pioreactor.utils.timing import catchtime


JobMetadataKey = int


class ShellKill:
    def __init__(self) -> None:
        self.list_of_pids: list[int] = []

    @staticmethod
    def safe_kill(*args: str) -> None:
        try:
            run(("kill", "-2") + args)
        except Exception:
            pass

    def append(self, pid: int) -> None:
        self.list_of_pids.append(pid)

    def kill_jobs(self) -> int:
        if len(self.list_of_pids) == 0:
            return 0

        self.safe_kill(*(str(pid) for pid in self.list_of_pids))

        return len(self.list_of_pids)


class LEDKill:
    def kill_jobs(self) -> int:
        try:
            run(("pio", "run", "led_intensity", "--A", "0", "--B", "0", "--C", "0", "--D", "0"))
            return 1
        except Exception:
            return 0


class JobManager:
    def __init__(self) -> None:
        db_path = config.get("storage", "temporary_cache")
        try:
            self.conn = sqlite3.connect(db_path, isolation_level=None)
            self.conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA busy_timeout = 5000;
                PRAGMA temp_store = 2;
                PRAGMA foreign_keys = ON;
                PRAGMA cache_size = -4000;
            """
            )
            self.cursor = self.conn.cursor()
            self._create_tables()
        except sqlite3.Error:
            raise OSError(f"Unable to open and create temporary_cache database at {db_path}")

    def _create_tables(self) -> None:
        create_table_query = """
        CREATE TABLE IF NOT EXISTS pio_job_metadata (
            job_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            unit         TEXT NOT NULL,
            experiment   TEXT NOT NULL,
            job_name     TEXT NOT NULL,
            job_source   TEXT NOT NULL,
            started_at   TEXT NOT NULL,
            is_running   INTEGER NOT NULL,
            leader       TEXT NOT NULL,
            pid          INTEGER NOT NULL,
            is_long_running_job INTEGER NOT NULL,
            ended_at     TEXT
        );

        CREATE TABLE IF NOT EXISTS pio_job_published_settings (
            setting        TEXT NOT NULL,
            value          BLOB,
            proposed_value BLOB,
            created_at     TEXT,
            updated_at     TEXT,
            job_id         INTEGER NOT NULL,
            FOREIGN KEY(job_id) REFERENCES pio_job_metadata(job_id),
            UNIQUE(setting, job_id)
        );

        CREATE INDEX IF NOT EXISTS idx_pio_job_metadata_is_running ON pio_job_metadata(is_running);
        CREATE INDEX IF NOT EXISTS idx_pio_job_metadata_is_running_experiment ON pio_job_metadata(is_running, experiment);
        CREATE INDEX IF NOT EXISTS idx_pio_job_metadata_job_name ON pio_job_metadata(job_name);

        CREATE INDEX IF NOT EXISTS idx_pio_job_published_settings_job_id ON pio_job_published_settings(job_id);
        CREATE UNIQUE INDEX IF NOT EXISTS  idx_pio_job_published_settings_setting_job_id ON pio_job_published_settings(setting, job_id);
        """
        self.cursor.executescript(create_table_query)

    def register_and_set_running(
        self,
        unit: pt.Unit,
        experiment: pt.Experiment,
        job_name: str,
        job_source: str | None,
        pid: int,
        leader: str,
        is_long_running_job: bool,
    ) -> JobMetadataKey:
        insert_query = "INSERT INTO pio_job_metadata (started_at, is_running, job_source, experiment, unit, job_name, leader, pid, is_long_running_job, ended_at) VALUES (STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'), 1, :job_source, :experiment, :unit, :job_name, :leader, :pid, :is_long_running_job, NULL);"

        self.cursor.execute(
            insert_query,
            {
                "unit": unit,
                "experiment": experiment,
                "job_source": job_source,
                "pid": pid,
                "leader": leader,
                "job_name": job_name,
                "is_long_running_job": is_long_running_job,
            },
        )
        assert isinstance(self.cursor.lastrowid, int)
        return self.cursor.lastrowid

    def does_pid_exist(self, pid: int) -> bool:
        # a proxy for: is this part of a larger job (ex: led intensity relationship to od_reading)
        self.cursor.execute("SELECT 1 FROM pio_job_metadata WHERE pid=(?) and is_running=1", (pid,))
        return self.cursor.fetchone() is not None

    def upsert_setting(self, job_id: JobMetadataKey, setting: str, value: Any) -> None:
        try:
            if value is None:
                # delete
                delete_query = """
                DELETE FROM pio_job_published_settings WHERE setting = :setting and job_id = :job_id
                """
                self.cursor.execute(delete_query, {"setting": setting, "job_id": job_id})
            else:
                # upsert
                update_query = """
                INSERT INTO pio_job_published_settings (setting, value, job_id, created_at, updated_at)
                VALUES (:setting, :value, :job_id, STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'), STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW'))
                    ON CONFLICT (setting, job_id) DO
                    UPDATE SET value = :value,
                                updated_at = STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
                """
                if isinstance(value, dict):
                    value = dumps(value).decode()  # back to string, not bytes
                elif isinstance(value, Struct):
                    value = str(value)  # complex type

                self.cursor.execute(
                    update_query,
                    {
                        "setting": setting,
                        "value": value,
                        "job_id": job_id,
                    },
                )

        except sqlite3.IntegrityError:
            # Can occur if the job row was removed before settings were upserted.
            return

    def set_not_running(self, job_id: JobMetadataKey) -> None:
        update_query = "UPDATE pio_job_metadata SET is_running=0, ended_at=STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW') WHERE job_id=(?)"
        self.cursor.execute(update_query, (job_id,))
        return

    def clear(self) -> None:
        """
        Remove all job metadata and published settings. Intended for tests.
        """
        self.cursor.execute("DELETE FROM pio_job_published_settings;")
        self.cursor.execute("DELETE FROM pio_job_metadata;")

    def is_job_running(self, job_name: str) -> bool:
        return self.get_running_job_id(job_name) is not None

    def get_running_job_id(self, job_name: str) -> int | None:
        select_query = """
            SELECT job_id
            FROM pio_job_metadata
            WHERE job_name = (?) AND is_running = 1
            ORDER BY started_at DESC
            LIMIT 1
        """
        self.cursor.execute(select_query, (job_name,))
        result = self.cursor.fetchone()
        return int(result[0]) if result else None

    def get_setting_from_running_job(self, job_name: str, setting: str, timeout=None) -> Any:
        if timeout is not None and not self.is_job_running(job_name):
            raise JobRequiredError(f"Job {job_name} is not running.")

        with catchtime() as timer:
            while True:
                select_query = """
                    SELECT value
                        FROM pio_job_published_settings s
                        JOIN pio_job_metadata m ON s.job_id = m.job_id
                    WHERE job_name=(?) and setting=(?) and is_running=1"""
                self.cursor.execute(select_query, (job_name, setting))
                result = self.cursor.fetchone()  # returns None if not found

                if result:
                    return result[0]

                if (timeout and timer() > timeout) or (timeout is None):
                    raise NameError(
                        f"Setting `{setting}` was not found in published settings of `{job_name}`."
                    )

    def _get_jobs(self, all_jobs: bool = False, **query) -> list[tuple[str, int, int]]:
        if not all_jobs:
            # Construct the WHERE clause based on the query parameters
            where_clause = " AND ".join([f"{key} = :{key}" for key in query.keys() if query[key] is not None])

            # Construct the SELECT query
            select_query = f"""
                SELECT
                    job_name,
                    pid,
                    job_id,
                    CASE
                        WHEN job_name LIKE "%pump%" THEN 1
                        WHEN job_name LIKE "%temperature%" THEN 1
                        WHEN job_name LIKE "%heat%" THEN 1
                        WHEN job_name LIKE "%pwm%" THEN 1
                        WHEN job_name LIKE "%_automation" THEN 2
                        WHEN job_name = "led_intensity" THEN 100
                    END as priority
                FROM pio_job_metadata
                WHERE is_running=1
                AND {where_clause}
                ORDER BY priority
            """

            # Execute the query and fetch the results
            self.cursor.execute(select_query, query)

        else:
            # Construct the SELECT query
            select_query = """SELECT
                    job_name,
                    pid,
                    job_id,
                    CASE
                        WHEN job_name LIKE "%pump%" THEN 1
                        WHEN job_name LIKE "%pwm%" THEN 1
                        WHEN job_name LIKE "%temperature%" THEN 2
                        WHEN job_name LIKE "%heat%" THEN 2
                        WHEN job_name LIKE "%_automation" THEN 3
                        ELSE 5
                    END as priority
                 FROM pio_job_metadata WHERE is_running=1 AND is_long_running_job=0
                ORDER BY priority"""

            # Execute the query and fetch the results
            self.cursor.execute(select_query)

        return self.cursor.fetchall()

    def list_jobs(self, all_jobs: bool = False, **query) -> list[tuple[str, int, int]]:
        """Return job rows matching *query* using the same filters as kill_jobs."""
        return self._get_jobs(all_jobs, **query)

    def list_job_history(
        self, running_only: bool = False
    ) -> list[tuple[int, str, str, str | None, str, str, str | None]]:
        where_clause = "WHERE ended_at IS NULL" if running_only else ""
        select_query = f"""
            SELECT
                job_id,
                job_name,
                experiment,
                job_source,
                unit,
                started_at,
                ended_at
            FROM pio_job_metadata
            {where_clause}
            ORDER BY started_at DESC
        """

        self.cursor.execute(select_query)
        return self.cursor.fetchall()

    def get_job_info(
        self, job_id: int
    ) -> tuple[int, str, str, str | None, str, str, str | None, int, str, int, int] | None:
        select_query = """
            SELECT job_id,
                job_name,
                experiment,
                job_source,
                unit,
                started_at,
                ended_at,
                is_running,
                leader,
                pid,
                is_long_running_job
            FROM pio_job_metadata
            WHERE job_id = ?
        """
        self.cursor.execute(select_query, (job_id,))
        return self.cursor.fetchone()

    def list_job_settings(self, job_id: int) -> list[tuple[str, Any, str, str | None]]:
        select_query = """
            SELECT setting, value, created_at, updated_at
            FROM pio_job_published_settings
            WHERE job_id = ?
            ORDER BY setting
        """
        self.cursor.execute(select_query, (job_id,))
        return self.cursor.fetchall()

    def remove_job(self, job_id: int) -> int:
        self.cursor.execute("DELETE FROM pio_job_published_settings WHERE job_id = ?", (job_id,))
        self.cursor.execute("DELETE FROM pio_job_metadata WHERE job_id = ?", (job_id,))
        return self.cursor.rowcount

    def kill_jobs(self, all_jobs: bool = False, **query) -> int:
        # ex: kill_jobs(experiment="testing_exp") should end all jobs with experiment='testing_exp'

        shell_kill = ShellKill()
        count = 0

        for job, pid, job_id, *_ in self._get_jobs(all_jobs, **query):
            if job == "led_intensity":
                if LEDKill().kill_jobs():
                    count += 1
                    self.set_not_running(job_id)

            else:
                shell_kill.append(pid)

        count += shell_kill.kill_jobs()

        return count

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "JobManager":
        return self

    def __exit__(self, exc_type, exc_val, tb) -> None:
        self.close()
        return


class ClusterJobManager:
    # this is a context manager to mimic the kill API for JobManager.
    def __init__(self) -> None:
        if not whoami.am_I_leader():
            raise RoleError("Must be leader to use this. Maybe you want JobManager?")

    @staticmethod
    def kill_jobs(
        units: tuple[pt.Unit, ...],
        all_jobs: bool = False,
        experiment: pt.Experiment | None = None,
        job_name: str | None = None,
        job_source: str | None = None,
        job_id: int | None = None,
    ) -> list[tuple[bool, dict]]:
        if len(units) == 0:
            return []

        body: dict[str, Any] = {}

        if all_jobs:
            endpoint = "/unit_api/jobs/stop/all"
        else:
            endpoint = "/unit_api/jobs/stop"

            if experiment:
                body["experiment"] = experiment
            if job_name:
                body["job_name"] = job_name
            if job_source:
                body["job_source"] = job_source
            if job_id:
                body["job_id"] = job_id

        def _thread_function(unit: pt.Unit) -> tuple[bool, dict]:
            try:
                r = patch_into(resolve_to_address(unit), endpoint, json=body)
                r.raise_for_status()
                return True, r.json()
            except Exception as e:
                print(f"Failed to send kill command to {unit}: {e}")
                return False, {"unit": unit}

        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            results = executor.map(_thread_function, units)

        return list(results)

    def __enter__(self) -> "ClusterJobManager":
        return self

    def __exit__(self, *args) -> None:
        return
