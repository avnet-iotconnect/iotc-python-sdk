import os
import pytest
import datetime as dt
import time

from iotconnect import IoTConnectSDK
from iotconnect.IoTConnectSDKException import IoTConnectSDKException

@pytest.fixture
def test_uid():
    return "sdktest"

@pytest.fixture
def test_sid():
    return "NTg0YWY3MzAyODU0NGE3NzhmM2JjYTE2OTY0MDFlMDg=UDE6MDM6MzUuMzk="

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

def test_instantiate_sdk(iotc_sdk):
    # Will pass if sdk is instantiated without error
    assert True

def test_instantiate_config(iotc_sdk):
    # Will pass if sdk is instantiated without error
    
    assert True

def test_instantiate_sdk_bad_1(test_sid, test_sdk_options):
    # Instantiate an SDK with an empty uId
    with pytest.raises(ValueError): 
        sdk = IoTConnectSDK("", test_sid, test_sdk_options)

def test_instantiate_sdk_bad_2(test_uid, test_sdk_options):
    # Instantiate an SDK with an empty sId
    with pytest.raises(ValueError):
        sdk = IoTConnectSDK(test_uid, "", test_sdk_options)

def test_message(iotc_sdk, test_uid):
    data = [{
        "uniqueId": test_uid,
        "time": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "data": {"Random_Integer": 42}
    }]
    iotc_sdk.SendData(data)
    