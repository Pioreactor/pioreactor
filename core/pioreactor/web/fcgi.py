#!/usr/bin/python3
# -*- coding: utf-8 -*-
from flup.server.fcgi import WSGIServer  # type: ignore
from pioreactor.web import tasks  # noqa: F401
from pioreactor.web.app import create_app


def main() -> None:
    WSGIServer(create_app()).run()


if __name__ == "__main__":
    main()
