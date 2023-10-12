import os
import datetime as dt
import time
import random

from iotconnect import IoTConnectSDK

uId = "sdktest"

with open("tests/test_certs/test_sid.txt", 'r') as f:
    sId = f.read()

sdkOptions = {
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

with IoTConnectSDK(uId, sId, sdkOptions) as iotc_sdk:
    try:
        while True:
            data = [{
                "uniqueId": uId,
                "time": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "data": {"Random_Integer": random.randint(1,100)}
            }]
            iotc_sdk.SendData(data)
            time.sleep(5)

    except KeyboardInterrupt:
        pass