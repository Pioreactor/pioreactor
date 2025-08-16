#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from flup.server.fcgi import WSGIServer
from pioreactor.web.app import create_app
from pioreactor.web.tasks import tasks  # noqa: F401


def main():
    WSGIServer(create_app()).run()


if __name__ == "__main__":
    main()
