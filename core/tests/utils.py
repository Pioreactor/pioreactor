# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from typing import Callable


def wait_for(predicate: Callable[[], bool], timeout: float = 5.0, check_interval: float = 0.05) -> bool:
    """
    Poll `predicate` until it returns True or timeout expires.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            # predicates used in tests may raise intermittently while state warms up
            pass
        time.sleep(check_interval)
    return False
