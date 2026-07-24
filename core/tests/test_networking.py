# -*- coding: utf-8 -*-
import subprocess
from typing import Iterator

import pytest
from pioreactor.utils import networking


@pytest.mark.parametrize(("returncode", "expected"), [(0, True), (1, False)])
def test_is_reachable_uses_ping_returncode(monkeypatch, returncode: int, expected: bool) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert args == (["ping", "-c1", "-W3", "worker.local"],)
        assert kwargs == {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "check": False,
        }
        return subprocess.CompletedProcess(args=args[0], returncode=returncode)

    monkeypatch.setattr(networking.subprocess, "run", fake_run)

    assert networking.is_reachable("worker.local") is expected


def test_get_ip_returns_comma_separated_stdout_addresses(monkeypatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args == (["hostname", "-I"],)
        assert kwargs == {"capture_output": True, "text": True, "check": False}
        return subprocess.CompletedProcess(
            args=["hostname", "-I"], returncode=0, stdout="192.168.1.5 10.0.0.2\n"
        )

    monkeypatch.setattr(networking.subprocess, "run", fake_run)

    assert networking.get_ip() == "192.168.1.5,10.0.0.2"


def test_get_ip_returns_empty_string_when_hostname_has_no_stdout(monkeypatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["hostname", "-I"], returncode=0, stdout="")

    monkeypatch.setattr(networking.subprocess, "run", fake_run)

    assert networking.get_ip() == ""


def test_get_ip_returns_empty_string_when_hostname_fails_without_stdout(monkeypatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["hostname", "-I"], returncode=1, stdout="")

    monkeypatch.setattr(networking.subprocess, "run", fake_run)

    assert networking.get_ip() == ""


def test_discover_workers_on_network_includes_hostname_and_ipv4(monkeypatch) -> None:
    class FakePopen:
        stdout: Iterator[str] = iter(
            [
                "=;eth0;IPv4;Pioreactor worker;_pio-worker._tcp;local;unit1.local;192.168.1.10;4999;",
                "=;lo;IPv4;Pioreactor worker;_pio-worker._tcp;local;ignored.local;127.0.0.1;4999;",
                "=;eth0;IPv6;Pioreactor worker;_pio-worker._tcp;local;ignored.local;fe80::1;4999;",
                "=;eth0;IPv4;Pioreactor worker;_pio-worker._tcp;local;unit2.local;192.168.1.11;4999;",
            ]
        )

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakePopen":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(networking.subprocess, "Popen", FakePopen)

    assert list(networking.discover_workers_on_network(terminate=True)) == [
        networking.DiscoveredWorker(hostname="unit1", ipv4_address="192.168.1.10"),
        networking.DiscoveredWorker(hostname="unit2", ipv4_address="192.168.1.11"),
    ]
