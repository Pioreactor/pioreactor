# -*- coding: utf-8 -*-
import subprocess
from typing import Iterator

from pioreactor.utils import networking


def test_get_ip_returns_non_loopback_addresses(monkeypatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args == (["ip", "-4", "-brief", "-j", "address"],)
        assert kwargs == {"capture_output": True, "text": True, "check": True}
        return subprocess.CompletedProcess(
            args=["ip", "-4", "-brief", "-j", "address"],
            returncode=0,
            stdout=(
                '[{"ifname":"lo","operstate":"UNKNOWN","addr_info":'
                '[{"local":"127.0.0.1","prefixlen":8}]},'
                '{"ifname":"wlan0","operstate":"UP","addr_info":'
                '[{"local":"192.168.0.20","prefixlen":24}]},'
                '{"ifname":"eth0","operstate":"UP","addr_info":'
                '[{"local":"10.0.0.2","prefixlen":24}]}]'
            ),
        )

    monkeypatch.setattr(networking.subprocess, "run", fake_run)

    assert networking.get_ip() == "192.168.0.20,10.0.0.2"


def test_get_ip_returns_empty_string_when_ip_has_no_stdout(monkeypatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["ip", "-4", "-brief", "-j", "address"], returncode=0, stdout=""
        )

    monkeypatch.setattr(networking.subprocess, "run", fake_run)

    assert networking.get_ip() == ""


def test_get_ip_returns_empty_string_when_ip_fails_without_stdout(monkeypatch) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(returncode=1, cmd=["ip", "-4", "-brief", "-j", "address"])

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
