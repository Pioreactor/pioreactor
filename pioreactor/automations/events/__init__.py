# -*- coding: utf-8 -*-
import re


class Event:

    message = None

    def __init__(self, message=""):
        self.message = message

    def __str__(self):
        if self.message:
            return f"{self.human_readable_name()}: {self.message}"
        else:
            return self.human_readable_name()

    def human_readable_name(self):
        name = type(self).__name__
        split = list(self.split_on_uppercase(name))
        return " ".join(map(lambda s: s.lower(), split))

    @staticmethod
    def split_on_uppercase(s):
        return filter(None, re.split("([A-Z][^A-Z]*)", s))


class NoEvent(Event):
    pass


class DilutionEvent(Event):
    pass


class AltMediaEvent(Event):
    pass


class IncreasedLuminosity(Event):
    pass


class RunningContinuously(Event):
    pass


class ErrorOccured(Event):
    pass
