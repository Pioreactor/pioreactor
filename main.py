# -*- coding: utf-8 -*-
from __future__ import annotations

import pioreactorui.tasks  # noqa: F401,F403 # Import tasks so they are registered with Huey instance.
from pioreactorui import create_app


if __name__ == "__main__":
    create_app().run()
