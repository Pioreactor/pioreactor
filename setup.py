# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name="morbidostat",
    version="0.1dev",
    license="MIT",
    long_description=open("README.md").read(),
    include_package_data=True,
    package_data={"": ["*.ini"]},
    packages=find_packages(exclude=["*.tests", "*.tests.*", "*benchmarks*"]),
)
