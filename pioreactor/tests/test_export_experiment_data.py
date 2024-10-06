# -*- coding: utf-8 -*-
# test_export_experiment_data.py
from __future__ import annotations

import re
import sqlite3
import zipfile
from unittest.mock import patch

import pytest

from pioreactor.actions.leader.export_experiment_data import export_experiment_data
from pioreactor.actions.leader.export_experiment_data import filter_to_timestamp_columns
from pioreactor.actions.leader.export_experiment_data import (
    generate_timestamp_to_localtimestamp_clause,
)
from pioreactor.actions.leader.export_experiment_data import get_column_names
from pioreactor.actions.leader.export_experiment_data import is_valid_table_name
from pioreactor.actions.leader.export_experiment_data import source_exists


def test_is_valid_table_name() -> None:
    assert is_valid_table_name("valid_table_name")
    assert not is_valid_table_name("invalid table name")
    assert not is_valid_table_name("123invalid")


def test_source_exists() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER)")
    cursor = conn.cursor()

    assert source_exists(cursor, "test_table")
    assert not source_exists(cursor, "nonexistent_table")


def test_get_column_names() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT, timestamp DATETIME)")
    cursor = conn.cursor()

    assert get_column_names(cursor, "test_table") == ["id", "name", "timestamp"]


def test_filter_to_timestamp_columns() -> None:
    columns = ["id", "name", "timestamp", "created_at", "updated_at"]
    assert filter_to_timestamp_columns(columns) == ["timestamp", "created_at", "updated_at"]


def test_generate_timestamp_to_localtimestamp_clause() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT, timestamp DATETIME, created_at DATETIME)")
    cursor = conn.cursor()

    assert (
        generate_timestamp_to_localtimestamp_clause(cursor, "test_table")
        == "datetime(timestamp, 'localtime') as timestamp_localtime,datetime(created_at, 'localtime') as created_at_localtime,"
    )


@pytest.fixture
def temp_zipfile(tmpdir):
    return tmpdir.join("test.zip")


def test_export_experiment_data(temp_zipfile) -> None:
    # Set up a temporary SQLite database with sample data
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT, timestamp DATETIME)")
    conn.execute("INSERT INTO test_table (id, name, timestamp) VALUES (1, 'John', '2021-09-01 00:00:00')")
    conn.commit()

    # Mock the connection and logger objects
    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value = conn

        export_experiment_data(
            experiment=None,
            output=temp_zipfile.strpath,
            partition_by_unit=False,
            tables=["test_table"],
        )

    # Check if the exported data is correct
    with zipfile.ZipFile(temp_zipfile.strpath, mode="r") as zf:
        # Find the file with a matching pattern
        csv_filename = None
        for filename in zf.namelist():
            if re.match(r"test_table-\d{14}\.csv", filename):
                csv_filename = filename
                break

        assert csv_filename is not None, "CSV file not found in the zipfile"

        with zf.open(csv_filename) as csv_file:
            content = csv_file.read().decode("utf-8").strip()
            headers, rows = content.split("\r\n")
            assert headers == "timestamp_localtime,id,name,timestamp"
            values = rows.split(",")
            assert values[1] == "1"
            assert values[2] == "John"
            assert values[3] == "2021-09-01 00:00:00"
            assert (
                values[0][:4] == "2021"
            )  # can't compare exactly since it uses datetime(ts, 'locatime') in sqlite3, and the localtime will vary between CI servers.


def test_export_experiment_data_with_experiment(temp_zipfile) -> None:
    # Set up a temporary SQLite database with sample data
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER, experiment TEXT, timestamp DATETIME)")
    conn.execute(
        "INSERT INTO test_table (id, experiment, timestamp) VALUES (1, 'test_export_experiment_data_with_experiment', '2021-09-01 00:00:00')"
    )
    conn.commit()

    # Mock the connection and logger objects
    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value = conn

        export_experiment_data(
            experiment="test_export_experiment_data_with_experiment",
            output=temp_zipfile.strpath,
            partition_by_unit=False,
            tables=["test_table"],
        )

    # Check if the exported data is correct
    with zipfile.ZipFile(temp_zipfile.strpath, mode="r") as zf:
        # Find the file with a matching pattern
        csv_filename = None
        for filename in zf.namelist():
            if re.match(r"test_export_experiment_data_with_experiment-test_table-\d{14}\.csv", filename):
                csv_filename = filename
                break

        assert csv_filename is not None, "CSV file not found in the zipfile"

        with zf.open(csv_filename) as csv_file:
            content = csv_file.read().decode("utf-8").strip()
            headers, rows = content.split("\r\n")
            assert headers == "timestamp_localtime,id,experiment,timestamp"
            values = rows.split(",")
            assert values[1] == "1"
            assert values[2] == "test_export_experiment_data_with_experiment"
            assert values[3] == "2021-09-01 00:00:00"
            assert (
                values[0][:4] == "2021"
            )  # can't compare exactly since it uses datetime(ts, 'locatime') in sqlite3, and the localtime will vary between CI servers.


def test_export_experiment_data_with_partition_by_unit(temp_zipfile) -> None:
    # Set up a temporary SQLite database with sample data
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE od_readings (pioreactor_unit TEXT, experiment TEXT, od_reading REAL, timestamp TEXT)"
    )
    conn.execute(
        """
    INSERT INTO od_readings (pioreactor_unit, experiment, od_reading, timestamp) VALUES ('pio01', 'exp1', 0.1, '2021-09-01 00:00:00'),
                                                                             ('pio02', 'exp1', 0.2, '2021-09-01 00:00:00'),
                                                                             ('pio01', 'exp1', 0.1, '2021-09-01 00:00:10'),
                                                                             ('pio02', 'exp1', 0.21, '2021-09-01 00:00:10'),
                                                                             ('pio01', 'exp1', 0.1, '2021-09-01 00:00:15'),
                                                                             ('pio02', 'exp1', 0.22, '2021-09-01 00:00:15'),
                                                                             ('pio02', 'exp2', 0.1, '2021-01-01 00:00:15'),
                                                                             ('pio02', 'exp2', 0.1, '2021-10-01 00:00:15');
    """
    )
    conn.commit()

    # Mock the connection and logger objects
    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value = conn

        export_experiment_data(
            experiment="exp1",
            output=temp_zipfile.strpath,
            partition_by_unit=True,
            tables=["od_readings"],
        )

    # Check if the exported data is correct
    with zipfile.ZipFile(temp_zipfile.strpath, mode="r") as zf:
        # Find the file with a matching pattern
        assert len(zf.namelist()) == 2
        assert "pio01" in sorted(zf.namelist())[0]
        assert "pio02" in sorted(zf.namelist())[1]


def test_export_experiment_data_with_partition_by_unit_if_pioreactor_unit_col_doesnt_exist(
    temp_zipfile,
) -> None:
    # Set up a temporary SQLite database with sample data
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE od_readings (experiment TEXT, od_reading REAL, timestamp TEXT)")
    conn.execute(
        """
    INSERT INTO od_readings (experiment, od_reading, timestamp) VALUES ('exp1', 0.1, '2021-09-01 00:00:00'),
                                                                       ('exp1', 0.2, '2021-09-01 00:00:00'),
                                                                       ('exp1', 0.1, '2021-09-01 00:00:10'),
                                                                       ('exp1', 0.21, '2021-09-01 00:00:10'),
                                                                       ('exp1', 0.1, '2021-09-01 00:00:15'),
                                                                       ('exp1', 0.22, '2021-09-01 00:00:15'),
                                                                       ('exp2', 0.1, '2021-01-01 00:00:15'),
                                                                       ('exp2', 0.1, '2021-10-01 00:00:15');
    """
    )
    conn.commit()

    # Mock the connection and logger objects
    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value = conn

        export_experiment_data(
            experiment="exp1",
            output=temp_zipfile.strpath,
            partition_by_unit=True,
            tables=["od_readings"],
        )

    # Check if the exported data is correct
    with zipfile.ZipFile(temp_zipfile.strpath, mode="r") as zf:
        # Find the file with a matching pattern
        assert len(zf.namelist()) == 1
        assert zf.namelist()[0].startswith("exp1-od_readings-all")
