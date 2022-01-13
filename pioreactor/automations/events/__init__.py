# -*- coding: utf-8 -*-
import re


class Event:

    message = None

    def __init__(self, message: str = "") -> None:
        self.message = message

    def __str__(self) -> str:
        if self.message:
            return f"{self.human_readable_name()}: {self.message}"
        else:
            return self.human_readable_name()

    def human_readable_name(self) -> str:
        name = type(self).__name__
        split = self.split_on_uppercase(name)
        return " ".join(map(lambda s: s.lower(), split))

    @staticmethod
    def split_on_uppercase(s) -> list[str]:
        return list(filter(None, re.split("([A-Z][^A-Z]*)", s)))


class NoEvent(Event):
    pass


class DilutionEvent(Event):
    pass


class AddMediaEvent(Event):
    pass


class AddAltMediaEvent(Event):
    pass


class ChangedLedIntensity(Event):
    pass


class RunningContinuously(Event):
    pass


class ErrorOccurred(Event):
    pass
