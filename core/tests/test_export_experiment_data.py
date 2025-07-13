# -*- coding: utf-8 -*-
# test_export_experiment_data.py
from __future__ import annotations

import re
import sqlite3
import zipfile
from unittest.mock import patch

import pytest
from pioreactor.actions.leader.export_experiment_data import export_experiment_data
from pioreactor.actions.leader.export_experiment_data import source_exists
from pioreactor.structs import Dataset


def test_source_exists() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER)")
    cursor = conn.cursor()

    assert source_exists(cursor, "test_table")
    assert not source_exists(cursor, "nonexistent_table")


@pytest.fixture
def mock_load_exportable_datasets():
    mock_datasets = {
        "test_table": Dataset(
            dataset_name="test_table",
            display_name="Test Table",
            table="test_table",
            has_unit=False,
            has_experiment=False,
            description="",
            default_order_by="timestamp",
            timestamp_columns=["timestamp"],
        ),
        "test_table_with_experiment": Dataset(
            dataset_name="test_table_with_experiment",
            display_name="Test Table",
            table="test_table_with_experiment",
            has_unit=False,
            has_experiment=True,
            description="",
            default_order_by="timestamp",
            timestamp_columns=["timestamp"],
        ),
        "od_readings": Dataset(
            dataset_name="od_readings",
            display_name="Test Table",
            table="od_readings",
            has_unit=True,
            has_experiment=True,
            description="",
            default_order_by="timestamp",
            timestamp_columns=["timestamp"],
        ),
        "test_base64": Dataset(
            dataset_name="test_base64",
            display_name="Test Table",
            query="SELECT id, BASE64(data) as data FROM test_base64",
            has_unit=False,
            has_experiment=False,
            description="",
            default_order_by=None,
        ),
    }
    with patch(
        "pioreactor.actions.leader.export_experiment_data.load_exportable_datasets",
        return_value=mock_datasets,
    ) as mock:
        yield mock


@pytest.fixture
def temp_zipfile(tmpdir):
    return tmpdir.join("test.zip")


def test_export_experiment_data(temp_zipfile, mock_load_exportable_datasets) -> None:
    # Set up a temporary SQLite database with sample data
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT, timestamp DATETIME, reading FLOAT)")
    conn.execute(
        "INSERT INTO test_table (id, name, timestamp, reading) VALUES (1, 'John', '2025-04-16T04:51:12.858Z', 0.04742762498678758)"
    )
    conn.commit()

    # Mock the connection and logger objects
    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value = conn

        export_experiment_data(
            experiments=[],
            output=temp_zipfile.strpath,
            partition_by_unit=False,
            dataset_names=["test_table"],
        )

    # Check if the exported data is correct
    with zipfile.ZipFile(temp_zipfile.strpath, mode="r") as zf:
        # Find the file with a matching pattern
        csv_filename = None
        for filename in zf.namelist():
            if re.match(r"test_table/test_table-all_experiments-all_units-\d{14}\.csv", filename):
                csv_filename = filename
                break

        assert csv_filename is not None, "CSV file not found in the zipfile"

        with zf.open(csv_filename) as csv_file:
            content = csv_file.read().decode("utf-8").strip()
            headers, rows = content.split("\r\n")
            assert headers == "id,name,timestamp,reading,timestamp_localtime"
            values = rows.split(",")
            assert values[0] == "1"
            assert values[1] == "John"
            assert values[2] == "2025-04-16T04:51:12.858Z"
            assert values[3] == "0.047427624987"
            assert (
                values[4][:4] == "2025"
            )  # can't compare exactly since it uses datetime(ts, 'locatime') in sqlite3, and the localtime will vary between CI servers.
            assert "12.858" in values[4]


def test_export_experiment_data_with_base64_data(temp_zipfile, mock_load_exportable_datasets) -> None:
    # Set up a temporary SQLite database with sample data
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_base64 (id INTEGER, data BLOB)")
    conn.execute(
        "INSERT INTO test_base64 (id, data) VALUES (1, 'eyJ2b2x1bWUiOjAuNSwiZHVyYXRpb24iOjIwLjAsInN0YXRlIjoiaW5pdCJ9')"
    )

    conn.commit()

    # Mock the connection and logger objects
    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value = conn

        export_experiment_data(
            experiments=[],
            output=temp_zipfile.strpath,
            partition_by_unit=False,
            dataset_names=["test_base64"],
        )

    # Check if the exported data is correct
    with zipfile.ZipFile(temp_zipfile.strpath, mode="r") as zf:
        # Find the file with a matching pattern
        csv_filename = None
        for filename in zf.namelist():
            if re.match(r"test_base64/test_base64-all_experiments-all_units-\d{14}\.csv", filename):
                csv_filename = filename
                break

        assert csv_filename is not None, "CSV file not found in the zipfile"

        with zf.open(csv_filename) as csv_file:
            content = csv_file.read().decode("utf-8").strip()
            headers, rows = content.split("\r\n")
            assert headers == "id,data"
            values = rows.split(",", maxsplit=1)
            assert values[0] == "1"
            assert values[1] == '"{""volume"":0.5,""duration"":20.0,""state"":""init""}"'


def test_export_experiment_data_with_experiment(temp_zipfile, mock_load_exportable_datasets) -> None:
    # Set up a temporary SQLite database with sample data
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table_with_experiment (id INTEGER, experiment TEXT, timestamp TEXT)")
    conn.execute(
        "INSERT INTO test_table_with_experiment (id, experiment, timestamp) VALUES (1, 'test_export_experiment_data_with_experiment', '2021-09-02 00:00:00')"
    )

    conn.execute("CREATE TABLE experiments (experiment TEXT, created_at TEXT)")
    conn.execute(
        "INSERT INTO experiments (experiment, created_at) VALUES ('test_export_experiment_data_with_experiment', '2021-09-01 00:00:00')"
    )
    conn.commit()

    # Mock the connection and logger objects
    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value = conn

        export_experiment_data(
            experiments=["test_export_experiment_data_with_experiment"],
            output=temp_zipfile.strpath,
            partition_by_unit=False,
            dataset_names=["test_table_with_experiment"],
        )

    # Check if the exported data is correct
    with zipfile.ZipFile(temp_zipfile.strpath, mode="r") as zf:
        # Find the file with a matching pattern
        csv_filename = None
        for filename in zf.namelist():
            if re.match(
                r"test_table_with_experiment/test_table_with_experiment-test_export_experiment_data_with_experiment-all_units-\d{14}\.csv",
                filename,
            ):
                csv_filename = filename
                break

        assert csv_filename is not None, "CSV file not found in the zipfile"

        with zf.open(csv_filename) as csv_file:
            content = csv_file.read().decode("utf-8").strip()
            headers, rows = content.split("\r\n")
            assert headers == "id,experiment,timestamp,timestamp_localtime,hours_since_experiment_created"
            values = rows.split(",")
            assert values[0] == "1"
            assert values[1] == "test_export_experiment_data_with_experiment"
            assert values[2] == "2021-09-02 00:00:00"
            assert (
                values[3][:4] == "2021"
            )  # can't compare exactly since it uses datetime(ts, 'locatime') in sqlite3, and the localtime will vary between CI servers.
            assert values[4] == "24.0"


def test_export_experiment_data_with_partition_by_unit(temp_zipfile, mock_load_exportable_datasets) -> None:
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
    conn.execute("CREATE TABLE experiments (experiment TEXT, created_at TEXT)")
    conn.execute("INSERT INTO experiments (experiment, created_at) VALUES ('exp2', '2021-09-01 00:00:00')")
    conn.execute("INSERT INTO experiments (experiment, created_at) VALUES ('exp1', '2021-09-01 00:00:00')")
    conn.commit()

    # Mock the connection and logger objects
    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value = conn

        export_experiment_data(
            experiments=["exp1"],
            output=temp_zipfile.strpath,
            partition_by_unit=True,
            dataset_names=["od_readings"],
        )

    # Check if the exported data is correct
    with zipfile.ZipFile(temp_zipfile.strpath, mode="r") as zf:
        # Find the file with a matching pattern
        assert len(zf.namelist()) == 3
        assert "od_readings/od_readings-exp1-pio01" in sorted(zf.namelist())[1]
        assert "od_readings/od_readings-exp1-pio02" in sorted(zf.namelist())[2]


def test_export_experiment_data_with_partition_by_unit_if_pioreactor_unit_col_doesnt_exist(
    temp_zipfile, mock_load_exportable_datasets
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
    conn.execute("CREATE TABLE experiments (experiment TEXT, created_at TEXT)")
    conn.execute("INSERT INTO experiments (experiment, created_at) VALUES ('exp2', '2021-09-01 00:00:00')")
    conn.execute("INSERT INTO experiments (experiment, created_at) VALUES ('exp1', '2021-09-01 00:00:00')")
    conn.commit()

    # Mock the connection and logger objects
    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value = conn

        export_experiment_data(
            experiments=["exp1"],
            output=temp_zipfile.strpath,
            partition_by_unit=True,
            dataset_names=["od_readings"],
        )

    # Check if the exported data is correct
    with zipfile.ZipFile(temp_zipfile.strpath, mode="r") as zf:
        # Find the file with a matching pattern
        assert len(zf.namelist()) == 2
    assert zf.namelist()[1].startswith("od_readings/od_readings-exp1-all_units")


def test_export_experiment_data_with_start_time(temp_zipfile, mock_load_exportable_datasets):
    # Set up a temporary SQLite database with sample data spanning two timestamps
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT, timestamp TEXT, reading FLOAT)")
    conn.execute(
        "INSERT INTO test_table (id, name, timestamp, reading) VALUES "
        "(1, 'A', '2021-09-01 00:00:00', 0.1),"
        "(2, 'B', '2021-09-01 00:00:10', 0.2)"
    )
    conn.commit()

    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value = conn
        export_experiment_data(
            experiments=[],
            output=temp_zipfile.strpath,
            partition_by_unit=False,
            dataset_names=["test_table"],
            start_time="2021-09-01 00:00:10",
        )

    with zipfile.ZipFile(temp_zipfile.strpath, mode="r") as zf:
        # Expect only the second row (id=2) matching start_time filter
        csv_filename = next(
            fn for fn in zf.namelist() if fn.startswith("test_table/") and fn.endswith(".csv")
        )
        with zf.open(csv_filename) as csv_file:
            content = csv_file.read().decode("utf-8").strip().splitlines()
            assert content[0] == "id,name,timestamp,reading,timestamp_localtime"
            # Only one data row should be present
            assert len(content) == 2
            values = content[1].split(",")
            assert values[0] == "2"


def test_export_experiment_data_with_end_time(temp_zipfile, mock_load_exportable_datasets):
    # Set up a temporary SQLite database with sample data spanning two timestamps
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT, timestamp TEXT, reading FLOAT)")
    conn.execute(
        "INSERT INTO test_table (id, name, timestamp, reading) VALUES "
        "(1, 'A', '2021-09-01 00:00:00', 0.1),"
        "(2, 'B', '2021-09-01 00:00:10', 0.2)"
    )
    conn.commit()

    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value = conn
        export_experiment_data(
            experiments=[],
            output=temp_zipfile.strpath,
            partition_by_unit=False,
            dataset_names=["test_table"],
            end_time="2021-09-01 00:00:00",
        )

    with zipfile.ZipFile(temp_zipfile.strpath, mode="r") as zf:
        # Expect only the first row (id=1) matching end_time filter
        csv_filename = next(
            fn for fn in zf.namelist() if fn.startswith("test_table/") and fn.endswith(".csv")
        )
        with zf.open(csv_filename) as csv_file:
            content = csv_file.read().decode("utf-8").strip().splitlines()
            assert content[0] == "id,name,timestamp,reading,timestamp_localtime"
            # Only one data row should be present
            assert len(content) == 2
            values = content[1].split(",")
            assert values[0] == "1"


def test_export_experiment_data_with_start_and_end_time(temp_zipfile, mock_load_exportable_datasets):
    # Set up a temporary SQLite database with sample data spanning two timestamps
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT, timestamp TEXT, reading FLOAT)")
    conn.execute(
        "INSERT INTO test_table (id, name, timestamp, reading) VALUES "
        "(1, 'A', '2021-09-01 00:00:00', 0.1),"
        "(2, 'B', '2021-09-01 00:00:10', 0.2),"
        "(3, 'C', '2021-09-01 00:00:20', 0.3)"
    )
    conn.commit()

    with patch("sqlite3.connect") as mock_connect:
        mock_connect.return_value = conn
        export_experiment_data(
            experiments=[],
            output=temp_zipfile.strpath,
            partition_by_unit=False,
            dataset_names=["test_table"],
            start_time="2021-09-01 00:00:10",
            end_time="2021-09-01 00:00:20",
        )

    with zipfile.ZipFile(temp_zipfile.strpath, mode="r") as zf:
        # Expect rows with id=2 and id=3 matching the time window
        csv_filename = next(
            fn for fn in zf.namelist() if fn.startswith("test_table/") and fn.endswith(".csv")
        )
        with zf.open(csv_filename) as csv_file:
            content = csv_file.read().decode("utf-8").strip().splitlines()
            assert content[0] == "id,name,timestamp,reading,timestamp_localtime"
            # Two data rows should be present
            rows = content[1:]
            assert len(rows) == 2
            ids = [row.split(",")[0] for row in rows]
            assert ids == ["2", "3"]
