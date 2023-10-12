import os
import pytest
import datetime as dt
import time

from iotconnect import IoTConnectSDK

def test_instantiate_sdk(iotc_sdk):
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

# def test_discovery_url():

