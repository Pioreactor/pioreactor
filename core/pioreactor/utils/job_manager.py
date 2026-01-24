# -*- coding: utf-8 -*-
import sqlite3
from subprocess import run
from typing import Any

from pioreactor import types as pt
from pioreactor.config import config


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
                ON CONFLICT(setting, job_id) DO UPDATE SET
                value = excluded.value,
                updated_at = STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW')
                """
                self.cursor.execute(update_query, {"setting": setting, "value": value, "job_id": job_id})

        except sqlite3.IntegrityError:
            # sometimes we hit a sqlite error if we try to upsert into a job that has been removed
            return

    def list_jobs(self, all_jobs: bool = False, **query) -> list[tuple]:
        return list(self._get_jobs(all_jobs=all_jobs, **query))

    def list_job_history(self) -> list[tuple]:
        self.cursor.execute(
            """
            SELECT job_id, job_name, experiment, job_source, unit, started_at, ended_at
            FROM pio_job_metadata
            ORDER BY job_id DESC
        """
        )
        return self.cursor.fetchall()

    def _get_jobs(self, all_jobs: bool = False, **query) -> list[tuple]:
        query_conditions: list[str] = []
        query_params: list = []

        if not all_jobs:
            query_conditions.append("is_running = 1")
        for key, value in query.items():
            if value is not None:
                query_conditions.append(f"{key} = ?")
                query_params.append(value)
        query_str = " AND ".join(query_conditions)
        if query_str:
            query_str = f"WHERE {query_str}"

        select_query = f"""
            SELECT job_name, pid, job_id, experiment, job_source, unit, started_at, ended_at, is_running, leader, is_long_running_job
            FROM pio_job_metadata
            {query_str}
        """
        self.cursor.execute(select_query, query_params)
        return self.cursor.fetchall()

    def set_not_running(self, job_id: JobMetadataKey) -> None:
        self.cursor.execute(
            "UPDATE pio_job_metadata SET is_running = 0, ended_at = STRFTIME('%Y-%m-%dT%H:%M:%fZ', 'NOW') WHERE job_id = ?",
            (job_id,),
        )

    def get_job_info(self, job_id: int) -> tuple | None:
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
