# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from typing import Generator
from typing import Optional


def cp_file_across_cluster(unit: str, localpath: str, remotepath: str):
    from sh import rsync  # type: ignore

    rsync(
        "-z",
        "--inplace",
        "-e",
        "ssh",
        localpath,
        f"{add_local(unit)}:{remotepath}",
    )


def is_using_local_access_point() -> bool:
    return os.path.isfile("/boot/local_access_point")


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


def default_gateway():
    # https://github.com/jonfairbanks/OctoPrint-NetworkHealth/blob/master/octoprint_NetworkHealth/__init__.py
    import socket
    import struct

    with open("/proc/net/route") as fh:
        for line in fh:
            fields = line.strip().split()
            if fields[1] != "00000000" or not int(fields[3], 16) & 2:
                continue
            return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))


def is_connected_to_network() -> bool:
    # https://github.com/jonfairbanks/OctoPrint-NetworkHealth/blob/master/octoprint_NetworkHealth/__init__.py
    hostname = default_gateway()
    if hostname is None:
        hostname = "8.8.8.8"
    response = os.system("ping -c 4 " + hostname)
    if response == 0:
        return True
    else:
        return False


def get_ip() -> Optional[str]:
    # returns ipv4
    from psutil import net_if_addrs

    interfaces = ["wlan0", "eth0"]

    for iface in interfaces:
        try:
            ipv4_addresses = [
                addr.address for addr in net_if_addrs()[iface] if addr.family == 2
            ]  # AddressFamily.AF_INET == 2
            if ipv4_addresses:
                return ipv4_addresses[0]
        except Exception:
            continue

    return None


def discover_workers_on_network(terminate: bool = False) -> Generator[str, None, None]:
    """
    Parameters
    ----------
    terminate: bool
        terminate after dumping a more or less complete list

    Example
    --------
    > for worker in discover_workers_on_network():
    >     print(worker)


    Notes
    ------

    This is very similar to `avahi-browse _pio-worker._tcp -t`

    """
    from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    from queue import Queue, Empty

    class Listener(ServiceListener):
        def __init__(self) -> None:
            self.hostnames: Queue[str] = Queue()

        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name)
            self.hostnames.put(info.server.removesuffix(".local."))  # type: ignore

        def remove_service(self, *args, **kwargs):
            pass

        def update_service(self, *args, **kwargs):
            pass

        def __next__(self) -> str:
            try:
                return self.hostnames.get(timeout=2 if terminate else None)
            except Empty:
                raise StopIteration

        def __iter__(self):
            return self

    listener = Listener()
    ServiceBrowser(Zeroconf(), "_pio-worker._tcp.local.", listener)
    yield from listener


def add_local(hostname: str) -> str:
    if not hostname.endswith(".local"):
        return hostname + ".local"
    return hostname
