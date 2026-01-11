# -*- coding: utf-8 -*-
from enum import Enum


class JobState(str, Enum):
    INIT = "init"
    READY = "ready"
    SLEEPING = "sleeping"
    DISCONNECTED = "disconnected"
    LOST = "lost"

    def __str__(self) -> str:
        return self.value
