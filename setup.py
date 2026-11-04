#!/usr/bin/env python3
from sys import exit, version_info
from setuptools import setup
from sftdyn import VERSION

if version_info[0] < 3:
    print("use python3 to install sftdyn (e.g. pip3)")
    exit(1)

setup(
    name="sftdyn",
    version=VERSION,
    description="HTTP(S)-based dynamic DNS updater server",
    long_description="dyndns.org-like service that accepts update requests " +
                     "via HTTP(S) and forwards them to a locally running " +
                     "DNS server via nsupdate.\n" +
                     "Works with most routers.\n" +
                     "Readme: " +
                     "https://github.com/skleber/sftdyn/blob/master/README.md",
    author="Michael Ensslin",
    author_email="michael@ensslin.cc",
    maintainer="Stephan Kleber",
    maintainer_email="stephan@skleber.de",
    url="https://github.com/skleber/sftdyn",
    license="GPL3+",
    packages=["sftdyn"],
    scripts=["bin/sftdyn"],
    entry_points={
        "console_scripts": [
            "sftdyn = sftdyn:main",
        ],
    },
    python_requires=">=3.10",
    install_requires=[
        "aiohttp>=3.8.0",
    ],
    extras_require={
        "test": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.20.0",
        ],
    },
    data_files=[
        ("/etc/sftdyn/", ["etc/sample.conf"]),
        ("/usr/lib/systemd/system/", ["etc/sftdyn.service"]),
    ],
    platforms=[
        'Linux',
    ],
    classifiers=[
        ("License :: OSI Approved :: "
         "GNU General Public License v3 or later (GPLv3+)"),
        "Topic :: Internet :: WWW/HTTP",
        "Intended Audience :: Developers",
        "Environment :: Console",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    ],
)
