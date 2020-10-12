# -*- coding: utf-8 -*-
import re


def split_on_uppercase(s):
    return filter(None, re.split("([A-Z][^A-Z]*)", s))


class Event:

    message = None

    def __init__(self, message=""):
        self.message = message

    def __str__(self):
        return f"{self.human_readable_name()}: {self.message}"

    def human_readable_name(self):
        name = type(self).__name__
        split = list(split_on_uppercase(name))
        return " ".join(map(lambda s: s.lower(), split))


class NoEvent(Event):
    pass


class DilutionEvent(Event):
    pass


class AltMediaEvent(Event):
    pass


class FlashUVEvent(Event):
    pass
