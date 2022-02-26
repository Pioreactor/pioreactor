# -*- coding: utf-8 -*-
from __future__ import annotations


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
    Can we ping the computer called `hostname`?
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


def get_ip() -> str:
    # psutil.net_if_addrs()?
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip
