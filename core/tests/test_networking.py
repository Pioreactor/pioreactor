# -*- coding: utf-8 -*-
from typing import Iterator

from pioreactor.utils import networking


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
