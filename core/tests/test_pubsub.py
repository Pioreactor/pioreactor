# -*- coding: utf-8 -*-
# test_pubsub.py
from __future__ import annotations

import socket
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from paho.mqtt.client import Client
from pioreactor.pubsub import add_hash_suffix
from pioreactor.pubsub import create_client
from pioreactor.pubsub import delete_from
from pioreactor.pubsub import delete_from_leader
from pioreactor.pubsub import get_from
from pioreactor.pubsub import get_from_leader
from pioreactor.pubsub import patch_into
from pioreactor.pubsub import patch_into_leader
from pioreactor.pubsub import post_into
from pioreactor.pubsub import post_into_leader
from pioreactor.pubsub import put_into
from pioreactor.pubsub import put_into_leader
from tests.conftest import capture_requests


def test_add_hash_suffix() -> None:
    s = "test_string"
    result = add_hash_suffix(s)
    assert len(result) == len(s) + 5  # 4 random characters and a hyphen
    assert result[: len(s)] == s
    assert result[len(s)] == "-"


@pytest.fixture
def mock_client():
    with patch("pioreactor.pubsub.Client") as mock_client:
        yield mock_client


def test_create_client_default_behavior(mock_client) -> None:
    hostname = "test_hostname"
    client_instance = MagicMock(spec=Client)
    mock_client.return_value = client_instance

    create_client(hostname=hostname)

    client_instance.username_pw_set.assert_called_with("pioreactor", "raspberry")
    client_instance.connect.assert_called_with(hostname, 1883, keepalive=60)
    client_instance.loop_start.assert_called_once()


def test_create_client_with_last_will(mock_client) -> None:
    hostname = "test_hostname"
    client_instance = MagicMock(spec=Client)
    mock_client.return_value = client_instance

    last_will = {"topic": "test/topic", "payload": "test_payload", "retain": True}

    create_client(hostname=hostname, last_will=last_will)

    client_instance.will_set.assert_called_with(**last_will)


def test_create_client_with_custom_on_connect(mock_client) -> None:
    hostname = "test_hostname"
    client_instance = MagicMock(spec=Client)
    mock_client.return_value = client_instance

    on_connect = MagicMock()
    create_client(hostname=hostname, on_connect=on_connect)

    assert client_instance.on_connect == on_connect


def test_create_client_with_custom_on_message(mock_client) -> None:
    hostname = "test_hostname"
    client_instance = MagicMock(spec=Client)
    mock_client.return_value = client_instance

    on_message = MagicMock()
    create_client(hostname=hostname, on_message=on_message)

    assert client_instance.on_message == on_message


def test_create_client_max_connection_attempts(mock_client) -> None:
    hostname = "test_hostname"
    client_instance = MagicMock(spec=Client)
    mock_client.return_value = client_instance
    client_instance.connect.side_effect = socket.gaierror()

    max_connection_attempts = 3
    create_client(hostname=hostname, max_connection_attempts=max_connection_attempts)

    assert client_instance.connect.call_count == max_connection_attempts


def test_post_into() -> None:
    data = b'{"key": "value"}'

    with capture_requests() as bucket:
        post_into("pio01.local", "/api/my_endpoint", body=data)

    # Check that the request was made
    assert len(bucket) == 1
    captured_request = bucket[0]

    # Assert request details
    assert captured_request.method == "POST"
    assert captured_request.url == "http://pio01.local:4999/api/my_endpoint"
    assert captured_request.body == data


def test_post_into_leader() -> None:
    data = b'{"key": "value"}'

    with capture_requests() as bucket:
        post_into_leader("/api/my_endpoint", body=data)

    # Check that the request was made
    assert len(bucket) == 1
    captured_request = bucket[0]

    # Assert request details
    assert captured_request.method == "POST"
    assert captured_request.url == "http://localhost:4999/api/my_endpoint"
    assert captured_request.body == data


def test_get_from() -> None:
    with capture_requests() as bucket:
        get_from("pio01.local", "/api/my_endpoint")

    assert len(bucket) == 1
    req = bucket[0]
    assert req.method == "GET"
    assert req.url == "http://pio01.local:4999/api/my_endpoint"


def test_get_from_leader() -> None:
    with capture_requests() as bucket:
        get_from_leader("/api/my_endpoint")

    assert len(bucket) == 1
    req = bucket[0]
    assert req.method == "GET"
    assert req.url == "http://localhost:4999/api/my_endpoint"


def test_put_into() -> None:
    data = b"payload"
    with capture_requests() as bucket:
        put_into("pio01.local", "/api/put_endpoint", body=data, json={"a": 1})

    assert len(bucket) == 1
    req = bucket[0]
    assert req.method == "PUT"
    assert req.url == "http://pio01.local:4999/api/put_endpoint"
    assert req.body == data
    assert req.json == {"a": 1}


def test_put_into_leader() -> None:
    data = b"payload"
    with capture_requests() as bucket:
        put_into_leader("/api/put_endpoint", body=data, json={"a": 1})

    assert len(bucket) == 1
    req = bucket[0]
    assert req.method == "PUT"
    assert req.url == "http://localhost:4999/api/put_endpoint"
    assert req.body == data
    assert req.json == {"a": 1}


def test_patch_into_and_patch_into_leader() -> None:
    data = b"patch"
    with capture_requests() as bucket:
        patch_into("piolocal", "/api/patch_endpoint", body=data, json={"b": 2})
        patch_into_leader("/api/patch_endpoint", body=data, json={"b": 2})

    assert len(bucket) == 2
    req1, req2 = bucket
    assert req1.method == "PATCH"
    assert req1.url == "http://piolocal:4999/api/patch_endpoint"
    assert req1.body == data
    assert req1.json == {"b": 2}

    assert req2.method == "PATCH"
    assert req2.url == "http://localhost:4999/api/patch_endpoint"
    assert req2.body == data
    assert req2.json == {"b": 2}


def test_delete_from_and_delete_from_leader() -> None:
    with capture_requests() as bucket:
        delete_from("host1", "/api/del_endpoint")
        delete_from_leader("/api/del_endpoint")

    assert len(bucket) == 2
    req1, req2 = bucket
    assert req1.method == "DELETE"
    assert req1.url == "http://host1:4999/api/del_endpoint"

    assert req2.method == "DELETE"
    assert req2.url == "http://localhost:4999/api/del_endpoint"
