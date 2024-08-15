# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
from queue import Empty
from queue import Queue
from threading import Thread
from typing import Generator
from typing import Optional


def cp_file_across_cluster(unit: str, localpath: str, remotepath: str, timeout: int = 5) -> None:
    from sh import rsync  # type: ignore
    from sh import ErrorReturnCode_30  # type: ignore

    try:
        rsync(
            "-z",
            "--timeout",
            timeout,
            "--inplace",
            "-e",
            "ssh",
            localpath,
            f"{add_local(unit)}:{remotepath}",
        )
    except ErrorReturnCode_30:
        raise ConnectionRefusedError(f"Error connecting to {unit}.")


def is_using_local_access_point() -> bool:
    return os.path.isfile("/boot/firmware/local_access_point")


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


def get_ip() -> Optional[str]:
    # returns all ipv4s as comma-separated string
    result = subprocess.run(["hostname", "-I"], stdout=subprocess.PIPE, text=True)
    ipv4_addresses = result.stdout.strip().split()
    if ipv4_addresses:
        return ",".join(ipv4_addresses)
    else:
        return None


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


def add_local(hostname: str) -> str:
    if not hostname.endswith(".local"):
        return hostname + ".local"
    return hostname
