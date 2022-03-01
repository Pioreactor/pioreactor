# -*- coding: utf-8 -*-
from __future__ import annotations

from setuptools import find_packages
from setuptools import setup

exec(compile(open("pioreactor/version.py").read(), "pioreactor/version.py", "exec"))


CORE_REQUIREMENTS = [
    "click>=8.0.4",
    "paho-mqtt>=1.6.0",
    "psutil>=5.9.0",
    "sh>=1.14.0",
    "JSON-log-formatter>=0.4.0",
    "colorlog>=6.6.0",
    "msgspec>=0.4.2",
    # tech debt - this needed to be in the core req
    # leader requirement
    "sqlite3worker @ https://github.com/pioreactor/sqlite3worker/archive/master.zip#egg=sqlite3worker-0.0.1",
]


LEADER_REQUIREMENTS = [
    "paramiko>=2.9.2",
]


WORKER_REQUIREMENTS = [
    "RPi.GPIO>=0.7.1",
    "adafruit-circuitpython-ads1x15>=2.2.12",
    "DAC43608>=0.2.6",
    "TMP1075>=0.2.0",
    "rpi-hardware-pwm>=0.1.4",
    "simple-pid>=1.0.1",
]

setup(
    name="pioreactor",
    version=__version__,  # type: ignore # noqa: F821g
    license="MIT",
    long_description=open("README.md").read(),
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
