# -*- coding: utf-8 -*-
from __future__ import annotations


class AutomationDict(dict):
    """
    A sublass for pretty printing
    """

    def __str__(self) -> str:
        s = f"{self['automation_name']}("
        for k, v in self.items():
            if k == "automation_name":
                continue
            s += f"{k}={v}, "

        s = s.rstrip(", ")
        s += ")"
        return s

    def __repr__(self) -> str:
        return str(self)
