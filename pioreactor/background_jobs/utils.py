# -*- coding: utf-8 -*-


class AutomationDict(dict):
    """
    A sublass for pretty printing
    """

    def __str__(self):
        s = f"{self['automation_key']}("
        for k, v in self.items():
            if k == "automation_key":
                continue
            s += f"{k}={v}, "

        s = s.rstrip(", ")
        s += ")"
        return s

    def __repr__(self):
        return str(self)
