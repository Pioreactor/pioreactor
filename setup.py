# -*- coding: utf-8 -*-
import fastentrypoints  # noqa: F401
from setuptools import setup, find_packages

exec(compile(open("pioreactor/version.py").read(), "pioreactor/version.py", "exec"))

with open("requirements/requirements.txt") as f:
    REQUIREMENTS = f.read().splitlines()


setup(
    name="pioreactor",
    version=__version__,  # noqa: F821
    license="MIT",
    long_description=open("README.md").read(),
    author_email="cam@pioreactor.com",
    install_requires=REQUIREMENTS,
    include_package_data=True,
    packages=find_packages(exclude=["*.tests", "*.tests.*"]),
    entry_points="""
        [console_scripts]
        pio=pioreactor.cli.pio:pio
        pios=pioreactor.cli.pios:pios
    """,
)
