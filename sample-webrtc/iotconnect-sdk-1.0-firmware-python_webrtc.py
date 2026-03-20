"""
  ******************************************************************************
  * @file   : iotconnect-sdk-1.0-firmware-python_webrtc.py
  * @author : Softweb Solutions An Avnet Company
  * @modify : 2025
  * @brief  : Firmware sample demonstrating KVS WebRTC signaling channel support
  *
  * Cloud command format to START WebRTC stream (ct=112):
  *   {"v":"2.1","ct":112,"webrtc":true,"carn":"arn:aws:kinesisvideo:us-east-1:612324506361:channel/gg08oct-VS26061/1772098142292"}
  *
  * Cloud command format to START GStreamer/PutMedia stream (ct=112):
  *   {"v":"2.1","ct":112,"webrtc":false}
  *   (or omit "webrtc" field entirely)
  *
  * Cloud command to STOP streaming (ct=113):
  *   {"v":"2.1","ct":113}
  *
  * WebRTC flow:
  *   1. Device receives ct=112 with webrtc=true and carn (channel ARN)
  *   2. SDK calls get_kinesis_cer() to fetch temporary AWS credentials via IoT Core
  *   3. Credentials are injected into a subprocess running kvsWebRTCClientMaster.py
  *   4. kvsWebRTCClientMaster.py connects to the KVS signaling channel as MASTER
  *   5. Viewer connects to the same channel and receives live video via WebRTC
  *
  * Device Identity Sync (VS object) auto-start behaviour:
  *   vs.as=true, vs.carn="<ARN>"  -> auto-start WebRTC signaling channel on connect
  *   vs.as=true, vs.carn=""       -> auto-start PutMedia (GStreamer/kvssink)
  *   vs.as=false                  -> wait for ct=112 cloud command
  *
  * This file has CHANNEL_ARN and CREDENTIAL_ENDPOINT hardcoded for direct device testing.
  * On startup it automatically starts WebRTC MASTER without needing a cloud command.
  ******************************************************************************
"""

import sys
import json
import time
import threading
from iotconnect import IoTConnectSDK
from datetime import datetime, timezone
import os

from iotconnect.client.awskinesisclient import start_kvs_webrtc_from_devicecert

# ---------------------------------------------------------------------------
# KVS WebRTC settings
# ---------------------------------------------------------------------------
CHANNEL_ARN         = "arn:aws:kinesisvideo:us-east-1:612324506361:channel/gg08oct-T160314WebRTC/1773745827647"
CREDENTIAL_ENDPOINT = "https://c1x1ly2rjmzjow.credentials.iot.us-east-1.amazonaws.com/role-aliases/kinesisvideoalias/credentials"

# ---------------------------------------------------------------------------
# Device identity - update for your device
# ---------------------------------------------------------------------------
UniqueId = "reInvent"

Sdk = None
interval = 10
directmethodlist = {}
ACKdirect = []
device_list = []
readyStatus = False

# ---------------------------------------------------------------------------
# SDK options - update certificate paths and environment settings
# ---------------------------------------------------------------------------
SdkOptions = {
    "certificate": {
        # Update these paths to where your device certificates are stored
        "SSLKeyPath"  : "/home/softweb/Ankit/webrtc/pk_VS26061.pem",       # device private key
        "SSLCertPath" : "/home/softweb/Ankit/webrtc/cert_VS26061.crt",      # device certificate
        "SSLCaPath"   : "/home/softweb/Ankit/AmazonrootCA.pem"             # Amazon Root CA
    },
    "offlineStorage": {
        "disabled": False,
        "availSpaceInMb": 0.01,
        "fileCount": 5,
        "keepalive": 60
    },
    "skipValidation": False,
    "discoveryUrl": "https://discovery.iotconnect.io",
    "IsDebug": True,
    "cpid": "mssql",
    "sId": "",
    "env": "preqa",
    "pf": "aws",

    # Camera settings used when ct=112 triggers a stream
    "CameraOptions": {
        "deviceport": "/dev/video0",
        "video": {
            "width": "640",
            "height": "480",
            "framerate": "30/1"
        }
    }
}


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def DeviceCallback(msg):
    """
    Receives device commands (ct=0) from the cloud.
    ct=112 (stream_start) and ct=113 (stream_stop) are handled internally
    by the SDK - you do not need to handle them here.
    """
    global Sdk
    print("Firmware :: --- Device Command Received ---")
    print("Firmware :: " + json.dumps(msg))

    cmdType = msg.get("ct") if msg else None

    if cmdType == 0:
        data = msg
        if data and data.get("ack"):
            if "id" in data:
                Sdk.sendAckCmd(data["ack"], 2, "successful", data["id"])
            else:
                Sdk.sendAckCmd(data["ack"], 2, "successful")
    else:
        print("Firmware :: rule/other command:", msg)


def DeviceFirmwareCallback(msg):
    global Sdk, device_list
    print("Firmware :: --- OTA Command Received ---")
    print("Firmware :: " + json.dumps(msg))

    cmdType = msg.get("ct") if msg else None
    if cmdType == 1:
        data = msg
        if data and data.get("urls"):
            for url_list in data["urls"]:
                if "tg" in url_list:
                    for i in device_list:
                        if "tg" in i and i["tg"] == url_list["tg"]:
                            Sdk.sendOTAAckCmd(data["ack"], 5, "successful", i["id"])
                else:
                    Sdk.sendOTAAckCmd(data["ack"], 5, "successful")


def DeviceConnectionCallback(msg):
    cmdType = msg.get("ct") if msg else None
    if cmdType == 116:
        print("Firmware :: Connection status: " + json.dumps(msg))


def TwinUpdateCallback(msg):
    global Sdk
    if msg:
        print("Firmware :: --- Twin Update Received ---")
        print("Firmware :: " + json.dumps(msg))
        if "desired" in msg and "reported" not in msg:
            for j in msg["desired"]:
                if j not in ("version", "uniqueId"):
                    Sdk.UpdateTwin(j, msg["desired"][j])


def DirectMethodCallback(msg, methodname, rId):
    global Sdk
    print("Firmware :: DirectMethod:", methodname, msg, rId)
    Sdk.DirectMethodACK(msg, 200, rId)


def DeviceChangCallback(msg):
    print("Firmware :: Device change:", msg)


def onReady(data):
    global readyStatus
    print("Firmware :: SDK ready:", str(data))
    readyStatus = True


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

def sendTelemetry(sdk):
    """Send a simple heartbeat telemetry to keep the connection alive."""
    dObj = [{
        "uniqueId": UniqueId,
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "data": {
            "uptime_s": int(time.monotonic())
        }
    }]
    if sdk.SendData(dObj):
        print("Firmware :: Telemetry sent")
    else:
        print("Firmware :: Telemetry send failed")


# ---------------------------------------------------------------------------
# WebRTC startup helper
#   Starts KVS WebRTC MASTER immediately on boot using the hardcoded
#   CHANNEL_ARN and CREDENTIAL_ENDPOINT above.
#   This is equivalent to the SDK receiving:
#     {"v":"2.1","ct":112,"webrtc":true,"carn":"<CHANNEL_ARN>"}
#   Or via device identity sync with vs.as=true and vs.carn=<CHANNEL_ARN>
# ---------------------------------------------------------------------------

def start_webrtc():
    """Start KVS WebRTC MASTER using the hardcoded channel ARN and credential endpoint."""
    certs = SdkOptions.get("certificate", {})
    ca_path   = certs.get("SSLCaPath")
    cert_path = certs.get("SSLCertPath")
    key_path  = certs.get("SSLKeyPath")

    # Extract thing name (uid) from the channel ARN.
    # ARN format: arn:aws:kinesisvideo:{region}:{account}:channel/{channel-name}/{timestamp}
    # e.g. arn:aws:kinesisvideo:us-east-1:612324506361:channel/gg08oct-T160314WebRTC/1773745827647
    #      -> uid = "gg08oct-T160314WebRTC"
    uid = CHANNEL_ARN.split('/')[-2]

    print("Firmware :: -----------------------------------------------")
    print("Firmware :: Starting KVS WebRTC MASTER")
    print(f"Firmware ::   Channel ARN : {CHANNEL_ARN}")
    print(f"Firmware ::   Cred EP     : {CREDENTIAL_ENDPOINT}")
    print(f"Firmware ::   Thing name  : {uid}")
    print(f"Firmware ::   Device cert : {cert_path}")
    print("Firmware :: -----------------------------------------------")

    threading.Thread(
        target=start_kvs_webrtc_from_devicecert,
        args=(
            CHANNEL_ARN,
            uid,
            ca_path,
            cert_path,
            key_path,
            CREDENTIAL_ENDPOINT,
            SdkOptions.get("CameraOptions", {})
            # region is auto-extracted from CHANNEL_ARN (us-east-1)
        ),
        daemon=True
    ).start()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global Sdk, device_list

    try:
        with IoTConnectSDK(UniqueId, SdkOptions, DeviceConnectionCallback) as Sdk:
            try:
                device_list = Sdk.Getdevice()
                Sdk.onDeviceCommand(DeviceCallback)
                Sdk.onTwinChangeCommand(TwinUpdateCallback)
                Sdk.onOTACommand(DeviceFirmwareCallback)
                Sdk.onDeviceChangeCommand(DeviceChangCallback)
                Sdk.getTwins()
                Sdk.onReady(onReady)

                for method in directmethodlist:
                    Sdk.regiter_directmethod_callback(method, DirectMethodCallback)

                device_list = Sdk.Getdevice()

                # Give SDK a moment to finish initialisation
                time.sleep(2)

                # Start KVS WebRTC MASTER immediately using hardcoded channel ARN
                start_webrtc()

                # Main telemetry loop - also responds to ct=112/113 from the cloud
                print("Firmware :: Entering telemetry loop...")
                while True:
                    sendTelemetry(Sdk)
                    time.sleep(interval)

                Sdk.Dispose()

            except KeyboardInterrupt:
                print("Firmware :: Interrupted")
                sys.exit(0)

    except Exception as ex:
        print(ex)


if __name__ == "__main__":
    main()
