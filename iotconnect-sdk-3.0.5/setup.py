import os
import sys
from setuptools import setup

packages_requires=[]

if 'win' in sys.platform:
    if sys.version_info >= (3, 6):
        packages_requires=["paho-mqtt","ntplib","pypiwin32"]
    else:
        packages_requires=[]
        os.system('pip install paho-mqtt')
        os.system('pip install ntplib')
        os.system('pip install pypiwin32')
        


elif 'linux' in sys.platform :
    if sys.version_info >= (3, 6):
        packages_requires=["paho-mqtt","ntplib"]
    else:
        packages_requires=[]
        os.system('pip install paho-mqtt')
        os.system('pip install ntplib')
        
 
setup(
    name="iotconnect-sdk",
    version="3.0.5",
    python_requires=">=2.7,>=3.5,>=3.11,<=3.12",
    description='SDK for D2C and C2D communication',
    license="MIT",
    author='SOFTWEB SOLUTIONS<admin@softwebsolutions.com> (https://www.softwebsolutions.com)',
    packages=["iotconnect", "iotconnect.client", "iotconnect.common"],
    install_requires=packages_requires,
    package_data={'iotconnect': ['assets/*.*']},
    platforms=['Linux', 'Mac OS X', 'Win'],
    zip_safe=False,
    classifiers=[
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.12",
        "License :: MIT License",
        "Operating System :: OS Independent"
    ],
)