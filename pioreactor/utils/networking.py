# -*- coding: utf-8 -*-
from __future__ import annotations

import ipaddress
import subprocess
from pathlib import Path
from queue import Empty
from queue import Queue
from threading import Thread
from typing import Generator

from pioreactor.exc import RsyncError


def rsync(*args):
    from subprocess import check_call
    from subprocess import CalledProcessError

    try:
        check_call(("rsync",) + args)
    except CalledProcessError as e:
        raise RsyncError from e


def cp_file_across_cluster(unit: str, localpath: str, remotepath: str, timeout: int = 5) -> None:
    try:
        rsync(
            "-z",
            "--timeout",
            f"{timeout}",
            "--inplace",
            "-e",
            "ssh",
            localpath,
            f"{resolve_to_address(unit)}:{remotepath}",
        )
    except RsyncError:
        raise RsyncError(f"Error moving file {localpath} to {unit}:{remotepath}.")


def is_using_local_access_point() -> bool:
    return Path("/boot/firmware/local_access_point").is_file()


def is_hostname_on_network(hostname: str, timeout: float = 10.0) -> bool:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((hostname, 22))
        s.close()
        return True
    except (socket.error, socket.timeout):
        return False


def is_reachable(address: str) -> bool:
    """
    Can we ping the computer at `address`?
    """
    # TODO: why not use sh.ping? Ex: ping("leader7.local", "-c1", "-W50")

    std_out_from_ping = subprocess.Popen(
        ["ping", "-c1", "-W50", address],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout
    if std_out_from_ping is not None:
        output = str(std_out_from_ping.read())
        # TODO: find a better test, or rethink above ping...
        return True if "1 received" in output else False
    return False


def get_ip() -> str:
    # returns all ipv4s as comma-separated string
    result = subprocess.run(["hostname", "-I"], stdout=subprocess.PIPE, text=True)
    ipv4_addresses = result.stdout.strip().split()
    if ipv4_addresses:
        return ",".join(ipv4_addresses)
    else:
        return ""


def discover_workers_on_network(terminate: bool = False) -> Generator[str, None, None]:
    """
    Discover workers on the network using avahi-browse.

    Parameters
    ----------
    terminate: bool
        If True, terminate after dumping a more or less complete list (wait 3 seconds for any new arrivals, exit if none).

    Yields
    ------
    str
        Hostnames of discovered workers.

    Example
    --------
    > for worker in discover_workers_on_network():
    >     print(worker)

    Notes
    -----
    This is very similar to `avahi-browse _pio-worker._tcp -tpr`
    """

    def worker_hostnames(queue: Queue) -> None:
        with subprocess.Popen(
            ["avahi-browse", "_pio-worker._tcp", "-rp"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        ) as process:
            if process.stdout is None:
                return

            assert process.stdout is not None
            for line in process.stdout:
                result = line.decode("utf8").rstrip("\n")
                parsed = result.split(";")
                if parsed[0] != "=" or parsed[1] == "lo" or parsed[2] != "IPv4":
                    continue
                hostname = parsed[6].removesuffix(".local")
                queue.put(hostname)
        return

    hostnames_queue: Queue[str] = Queue()
    worker_thread = Thread(target=worker_hostnames, args=(hostnames_queue,))
    worker_thread.daemon = True
    worker_thread.start()

    while True:
        try:
            # Wait for the next hostname, with a timeout if terminate is True
            hostname = hostnames_queue.get(timeout=3 if terminate else None)
            yield hostname
        except Empty:
            # If the queue is empty and we're in terminate mode, stop the iteration
            if terminate:
                break


def resolve_to_address(hostname: str) -> str:
    # TODO: make this more fleshed out: resolve to IP, etc.
    # add_local assumes a working mDNS.
    return add_local(hostname)


def add_local(hostname: str) -> str:
    try:
        # if it looks like an IP, don't continue
        ipaddress.ip_address(hostname)
        return hostname
    except ValueError:
        pass
    if not hostname.endswith(".local"):
        return hostname + ".local"
    return hostname
