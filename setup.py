# -*- coding: utf-8 -*-
from __future__ import annotations

from setuptools import find_packages
from setuptools import setup

exec(compile(open("pioreactor/version.py").read(), "pioreactor/version.py", "exec"))


CORE_REQUIREMENTS = [
    "click==8.1.3",
    "paho-mqtt==1.6.1",
    "psutil==5.9.4",
    "sh==1.14.3",
    "JSON-log-formatter==0.5.1",
    "colorlog==6.7.0",
    "msgspec==0.14.2",
    "diskcache==5.4.0",
    "wheel==0.38.4",
    "crudini==0.9.4",
    # tech debt - this needed to be in the core req
    # leader requirement
    # this direct dependency also prevents us from uploading to PyPI...
    "sqlite3worker @ https://github.com/pioreactor/sqlite3worker/archive/master.zip#egg=sqlite3worker-0.0.1",
]


UI_REQUIREMENTS = [
    # pyyaml is installed elsewhere
    "flask==2.2.2",
    "flup6==1.1.1",
    "python-dotenv==0.21.0",
    "huey==2.4.3",
]


LEADER_REQUIREMENTS = ["zeroconf==0.47.1"] + UI_REQUIREMENTS


WORKER_REQUIREMENTS = [
    "RPi.GPIO==0.7.1",
    "adafruit-circuitpython-ads1x15==2.2.12",
    "DAC43608==0.2.7",
    "TMP1075==0.2.1",
    "rpi-hardware-pwm==0.1.4",
    "simple-pid==1.0.1",
    "plotext>=5.2.8",
]

setup(
    name="pioreactor",
    version=__version__,  # type: ignore # noqa: F821
    license="MIT",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Pioreactor",
    author_email="cam@pioreactor.com",
    install_requires=CORE_REQUIREMENTS,
    include_package_data=True,
    packages=find_packages(exclude=["*.tests", "*.tests.*"]),
    entry_points="""
        [console_scripts]
        pio=pioreactor.cli.pio:pio
        pios=pioreactor.cli.pios:pios
    """,
    python_requires=">=3.9",
    extras_require={
        "leader": LEADER_REQUIREMENTS,
        "worker": WORKER_REQUIREMENTS,
        "leader_worker": LEADER_REQUIREMENTS + WORKER_REQUIREMENTS,
    },
)
