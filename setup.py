# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open("requirements.txt") as f:
    REQUIREMENTS = f.read().splitlines()


setup(
    name="morbidostat",
    version="0.1dev0",
    license="MIT",
    long_description=open("README.md").read(),
    include_package_data=True,
    install_requires=["click"],
    package_data={"": ["*.ini"]},
    packages=find_packages(exclude=["*.tests", "*.tests.*", "*benchmarks*"]),
    entry_points="""
        [console_scripts]
        morbidostat=morbidostat.command_line:cli
    """,
)
