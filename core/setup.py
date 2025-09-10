# -*- coding: utf-8 -*-
from __future__ import annotations

from setuptools import find_packages
from setuptools import setup

exec(compile(open("pioreactor/version.py").read(), "pioreactor/version.py", "exec"))


CORE_REQUIREMENTS = [
    "click==8.1.7",
    "paho-mqtt==2.1.0",
    "JSON-log-formatter==0.5.1",
    "colorlog==6.7.0",
    "msgspec==0.19.0",
    "crudini==0.9.5",
    "iniparse==0.5",
    "blinker==1.9.0",
    "Flask==3.1.0",
    "flup6==1.1.1",
    "huey==2.5.2",
    "itsdangerous==2.2.0",
    "Jinja2==3.1.4",
    "MarkupSafe==2.1.5",
    "python-dotenv==1.0.1",
    "Werkzeug==3.1.0",
    "packaging==24.1",
    "mcp_utils @ git+https://github.com/pioreactor/mcp-utils.git@242a8e1",
]


LEADER_REQUIREMENTS: list[str] = []


WORKER_REQUIREMENTS = [
    "grpredict==25.6.1",
    "Adafruit-Blinka==8.58.1",
    "adafruit-circuitpython-ads1x15==2.2.23",
    "adafruit-circuitpython-busdevice==5.2.9",
    "adafruit-circuitpython-connectionmanager==3.1.1",
    "adafruit-circuitpython-requests==4.1.3",
    "adafruit-circuitpython-typing==1.10.3",
    "Adafruit-PlatformDetect==3.78.0",
    "Adafruit-PureIO==1.1.11",
    "plotext==5.2.8",
    "pyftdi==0.55.4",
    "pyserial==3.5",
    "pyusb==1.2.1",
    "rpi_hardware_pwm==0.3.0",
    "smbus2==0.5.0",
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
    packages=find_packages(exclude=["tests", "tests.*"]),
    entry_points="""
        [console_scripts]
        pio=pioreactor.cli.pio:pio
        pios=pioreactor.cli.pios:pios
    """,
    python_requires=">=3.11",
    extras_require={
        "worker": WORKER_REQUIREMENTS,
        "leader_worker": LEADER_REQUIREMENTS + WORKER_REQUIREMENTS,
        "leader": LEADER_REQUIREMENTS + WORKER_REQUIREMENTS,
    },
)
