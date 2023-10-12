import pytest
import datetime as dt

from iotconnect import IoTConnectSDK

def test_message(iotc_sdk, test_uid):
    data = [{
        "uniqueId": test_uid,
        "time": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "data": {"Random_Integer": 42}
    }]
    iotc_sdk.SendData(data)

def test_ack_msg(iotc_sdk):
    device_msg = {
        "ct": 0,
        "v": 2.1,
        "cmd": "A String represents the command text",
        "ack": "A string represents guid as the acknowledgement id",
    }

def test_post_call(iotc_sdk):
    response = iotc_sdk.post_call(iotc_sdk._identity_base_url)
    print(f"\nResponse:\n{response}")
