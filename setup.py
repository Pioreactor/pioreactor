# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open("requirements/requirements.txt") as f:
    REQUIREMENTS = f.read().splitlines()


setup(
    name="morbidostat",
    version="0.1.dev0",
    license="MIT",
    long_description=open("README.md").read(),
    install_requires=REQUIREMENTS,
    include_package_data=True,
    package_data={"morbidostat": ["config.ini"]},
    packages=find_packages(exclude=["*.tests", "*.tests.*", "*benchmarks*"]),
    entry_points="""
        [console_scripts]
        mb=morbidostat.command_line_worker:cli
        mba=morbidostat.command_line_leader:cli
    """,
)
