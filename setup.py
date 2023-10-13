# -*- coding: utf-8 -*-
from __future__ import annotations

from setuptools import find_packages
from setuptools import setup

exec(compile(open("pioreactor/version.py").read(), "pioreactor/version.py", "exec"))


CORE_REQUIREMENTS = [
    "click==8.1.7",
    "paho-mqtt==1.6.1",
    "psutil==5.9.5",
    "sh==2.0.6",
    "JSON-log-formatter==0.5.1",
    "colorlog==6.7.0",
    "msgspec==0.18.4",
    "diskcache==5.6.3",
    "wheel==0.41.2",
    "crudini==0.9.5",
    'lgpio; platform_machine != "armv7l"',
]


UI_REQUIREMENTS = [
    # pyyaml is installed elsewhere
    "flask==2.2.2",
    "flup6==1.1.1",
    "python-dotenv==0.21.0",
    "huey==2.4.5",
]


LEADER_REQUIREMENTS = ["zeroconf==0.115.2"] + UI_REQUIREMENTS


WORKER_REQUIREMENTS = [
    "adafruit-circuitpython-ads1x15==2.2.23",
    "DAC43608==0.2.7",
    "TMP1075==0.2.1",
    "rpi-hardware-pwm==0.1.4",
    "plotext==5.2.8",
]

setup(
    name="pioreactor",
    version=__version__,  # type: ignore # noqa: F821
    license="MIT",
    description="The core Python app of the Pioreactor. Control your bioreactor through Python.",
    url="https://github.com/pioreactor/pioreactor",
    classifiers=[
        "Topic :: Scientific/Engineering",
        "Topic :: System :: Hardware",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Education",
        "Development Status :: 5 - Production/Stable",
    ],
    keywords=["microbiology", "bioreactor", "turbidostat", "raspberry pi", "education", "research"],
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Pioreactor",
    author_email="hello@pioreactor.com",
    install_requires=CORE_REQUIREMENTS,
    include_package_data=True,
    packages=find_packages(exclude=["*.tests", "*.tests.*"]),
    entry_points="""
        [console_scripts]
        pio=pioreactor.cli.pio:pio
        pios=pioreactor.cli.pios:pios
    """,
    python_requires=">=3.11",
    extras_require={
        "leader": LEADER_REQUIREMENTS,
        "worker": WORKER_REQUIREMENTS,
        "leader_worker": LEADER_REQUIREMENTS + WORKER_REQUIREMENTS,
    },
)
