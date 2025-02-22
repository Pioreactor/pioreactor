# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
from pathlib import Path
from queue import Empty
from queue import Queue
from threading import Thread
from typing import Generator

from pioreactor.config import config
from pioreactor.exc import RsyncError
from pioreactor.exc import SSHError


def ssh(address: str, command: str):
    try:
        detached_command = f"nohup {command} > /dev/null 2>&1 &"  # this assumes I want to detach!
        subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", address, detached_command],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise SSHError(f"SSH command failed: {e.stderr}") from e


def rsync(*args: str) -> None:
    try:
        subprocess.run(
            ("rsync",) + args,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        raise RsyncError(f"rysnc command failed: {e.stderr}") from e


def cp_file_across_cluster(
    unit: str, localpath: str, remotepath: str, timeout: int = 5, user="pioreactor"
) -> None:
    try:
        rsync(
            "-z",
            "--timeout",
            f"{timeout}",
            "--inplace",
            "--checksum",
            localpath,
            f"{user}@{resolve_to_address(unit)}:{remotepath}",
        )
    except RsyncError:
        raise RsyncError(f"Error moving file {localpath} to {unit}:{remotepath}.")


def is_using_local_access_point() -> bool:
    return Path("/boot/firmware/local_access_point").exists()


def is_address_on_network(address: str, timeout: float = 10.0) -> bool:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((address, 22))
        s.close()
        return True
    except (socket.error, socket.timeout):
        return False


def is_reachable(address: str) -> bool:
    """
    Can we ping the computer at `address`?
    """
    std_out_from_ping = subprocess.Popen(
        ["ping", "-c1", "-W3", address],
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
    result = subprocess.run(
        r"hostname -I | grep -Eo '([0-9]*\.){3}[0-9]*' | tr '\n' '\n'",
        capture_output=True,
        text=True,
        shell=True,
    )
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
    address_in_config = config.get("cluster.addresses", hostname, fallback=None)
    if address_in_config is not None:
        return address_in_config
    else:
        return add_local(hostname)


def add_local(hostname: str) -> str:
    hostname_lower = hostname.lower()

    # Check if it's localhost first
    if hostname_lower == "localhost":
        return hostname

    # Check if it's a valid IP address
    try:
        import ipaddress

        ipaddress.ip_address(hostname)
        return hostname
    except ValueError:
        pass

    # Add .local if not already present
    if not hostname_lower.endswith(".local"):
        return hostname + ".local"

    return hostname
