# -*- coding: utf-8 -*-
# test_export_experiment_data.py
from __future__ import annotations

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


def test_is_valid_table_name():
    assert is_valid_table_name("valid_table_name")
    assert not is_valid_table_name("invalid table name")
    assert not is_valid_table_name("123invalid")


def test_source_exists():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER)")
    cursor = conn.cursor()

    assert source_exists(cursor, "test_table")
    assert not source_exists(cursor, "nonexistent_table")


def test_get_column_names():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT, timestamp DATETIME)")
    cursor = conn.cursor()

    assert get_column_names(cursor, "test_table") == ["id", "name", "timestamp"]


def test_filter_to_timestamp_columns():
    columns = ["id", "name", "timestamp", "created_at", "updated_at"]
    assert filter_to_timestamp_columns(columns) == ["timestamp", "created_at", "updated_at"]


def test_generate_timestamp_to_localtimestamp_clause():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE test_table (id INTEGER, name TEXT, timestamp DATETIME, created_at DATETIME)"
    )
    cursor = conn.cursor()

    assert (
        generate_timestamp_to_localtimestamp_clause(cursor, "test_table")
        == "datetime(timestamp, 'localtime') as timestamp_localtime,datetime(created_at, 'localtime') as created_at_localtime,"
    )


@pytest.fixture
def temp_zipfile(tmpdir):
    return tmpdir.join("test.zip")


import re


def test_export_experiment_data(temp_zipfile):
    # Set up a temporary SQLite database with sample data
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT, timestamp DATETIME)")
    conn.execute(
        "INSERT INTO test_table (id, name, timestamp) VALUES (1, 'John', '2021-09-01 00:00:00')"
    )
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
            content = csv_file.read().decode("utf-8")
            assert (
                content.strip()
                == "timestamp_localtime,id,name,timestamp\r\n2021-08-31 20:00:00,1,John,2021-09-01 00:00:00"
            )


def test_export_experiment_data_with_experiment(temp_zipfile):
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
            if re.match(
                r"test_export_experiment_data_with_experiment-test_table-\d{14}\.csv", filename
            ):
                csv_filename = filename
                break

        assert csv_filename is not None, "CSV file not found in the zipfile"

        with zf.open(csv_filename) as csv_file:
            content = csv_file.read().decode("utf-8")
            assert (
                content.strip()
                == "timestamp_localtime,id,experiment,timestamp\r\n2021-08-31 20:00:00,1,test_export_experiment_data_with_experiment,2021-09-01 00:00:00"
            )
