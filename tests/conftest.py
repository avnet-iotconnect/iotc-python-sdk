import os
import pytest
import datetime as dt

from iotconnect import IoTConnectSDK

@pytest.fixture
def test_uid():
    return "sdktest"

@pytest.fixture
def test_sid():
    with open("tests/test_certs/test_sid.txt", 'r') as f:
        return f.read()

@pytest.fixture
def test_sdk_options():
    return {
        "certificate" : { 
            "SSLKeyPath"  : os.path.abspath("./tests/test_certs/test_pk.pem"), 
            "SSLCertPath" : os.path.abspath("./tests/test_certs/test_cert.crt"),
            "SSLCaPath"   : os.path.abspath("./tests/root-CA.pem")
        },
        "offlineStorage":{
            "disabled": False,
            "availSpaceInMb": 0.01,
            "fileCount": 5,
            "keepalive":60
        },
        "skipValidation": False,
        "discoveryUrl": "https://awsdiscovery.iotconnect.io",
        "IsDebug": True
    }


@pytest.fixture
def iotc_sdk(test_uid, test_sid, test_sdk_options):
    return IoTConnectSDK(test_uid, test_sid, test_sdk_options)