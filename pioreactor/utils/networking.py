# -*- coding: utf-8 -*-
import socket


def is_hostname_on_network(hostname: str) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((hostname, 22))
        s.close()
        return True
    except socket.error:
        return False


def is_reachable(hostname: str) -> bool:
    import subprocess

    ping_response = str(
        subprocess.Popen(
            ["ping", "-c1", "-W50", hostname],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ).stdout.read()
    )
    # TODO: find a better test, or rethink above ping...
    return True if "1 received" in ping_response else False


def is_allowable_hostname(hostname: str) -> bool:
    import re

    return True if re.match(r"^[0-9a-zA-Z\-]+$", hostname) else False


def get_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip
