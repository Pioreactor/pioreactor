#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from flup.server.fcgi import WSGIServer

import pioreactorui.tasks  # noqa: F401
from pioreactorui import create_app


if __name__ == "__main__":
    WSGIServer(create_app()).run()
