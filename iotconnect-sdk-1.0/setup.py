import os
import sys
from setuptools import setup

packages_requires = [
    "paho-mqtt>=1.6.0",
    "ntplib>=0.4.0",
    "requests>=2.20.0",
]

if 'win' in sys.platform:
    packages_requires.append("pypiwin32>=223")

setup(
    name="iotconnect-sdk",
    version="1.0",
    python_requires=">=3.5",
    description='SDK for D2C and C2D communication',
    license="MIT",
    author='SOFTWEB SOLUTIONS<admin@softwebsolutions.com> (https://www.softwebsolutions.com)',
    packages=["iotconnect", "iotconnect.client", "iotconnect.common"],
    install_requires=packages_requires,
    package_data={'iotconnect': ['assets/*.*']},
    platforms=['Linux', 'Mac OS X', 'Win'],
    zip_safe=False,
    classifiers=[
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent"
    ],
)
