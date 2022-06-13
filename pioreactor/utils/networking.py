# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Optional


def is_hostname_on_network(hostname: str) -> bool:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((hostname, 22))
        s.close()
        return True
    except socket.error:
        return False


def is_reachable(hostname: str) -> bool:
    """
    Can we ping the computer at `hostname`?
    """
    import subprocess

    std_out_from_ping = subprocess.Popen(
        ["ping", "-c1", "-W50", hostname],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout
    if std_out_from_ping is not None:
        output = str(std_out_from_ping.read())
        # TODO: find a better test, or rethink above ping...
        return True if "1 received" in output else False
    return False


def get_ip() -> Optional[str]:
    from psutil import net_if_addrs

    try:
        return net_if_addrs()["wlan0"][0].address
    except Exception:
        return None


def discover_workers_on_network() -> list[str]:
    import time
    from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

    class Listener(ServiceListener):
        def __init__(self):
            self.hostnames: list[str] = []

        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name)
            self.hostnames.append(info.server.removesuffix(".local."))

        def update_service(self, *args, **kwargs):
            pass

    listener = Listener()
    ServiceBrowser(Zeroconf(), "_pioreactor_worker._tcp.local.", listener)
    time.sleep(1)
    return listener.hostnames
