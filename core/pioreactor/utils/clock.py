# -*- coding: utf-8 -*-
from subprocess import CalledProcessError
from subprocess import run
from subprocess import TimeoutExpired


def is_clock_synchronized() -> bool | None:
    """Read the system's NTP sync state; unavailable or unrecognized status is unknown."""
    try:
        result = run(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, CalledProcessError, TimeoutExpired):
        return None

    return {"yes": True, "no": False}.get(result.stdout.strip())
