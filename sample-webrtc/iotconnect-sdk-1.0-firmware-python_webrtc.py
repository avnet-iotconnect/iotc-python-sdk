"""
  ******************************************************************************
  * @file   : iotconnect-sdk-1.0-firmware-python_webrtc.py
  * @author : Softweb Solutions An Avnet Company
  * @modify : 2025
  * @brief  : Firmware sample demonstrating KVS WebRTC signaling channel support
  *
  * This firmware does NOT hardcode any channel ARN. Instead it relies on the
  * SDK's device sync response which provides the video stream (VS) object:
  *
  *   vs.as   = true/false   (auto-start flag)
  *   vs.carn = "<ARN>"      (KVS signaling channel ARN)
  *
  * Behaviour:
  *   - If vs.as=true and vs.carn is set  -> SDK auto-starts WebRTC MASTER
  *   - If vs.as=true and vs.carn is empty -> SDK auto-starts GStreamer/PutMedia
  *   - If vs.as=false -> SDK waits for ct=112 cloud command to start streaming
  *
  * Cloud command format to START WebRTC stream (ct=112):
  *   {"v":"2.1","ct":112,"webrtc":true,"carn":"arn:aws:kinesisvideo:..."}
  *
  * Cloud command to STOP streaming (ct=113):
  *   {"v":"2.1","ct":113}
  *
  * The firmware developer only needs to:
  *   1. Set the correct UniqueId (device identity)
  *   2. Provide certificate paths
  *   3. Configure CameraOptions for the device
  *   4. The SDK handles everything else (credential fetch, WebRTC startup)
  ******************************************************************************
"""

import sys
import json
import time
from iotconnect import IoTConnectSDK
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Device identity - update for your device
# ---------------------------------------------------------------------------
UniqueId = "WebRTC-D01"

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
        "SSLKeyPath"  : "C:/Users/ankit.sangani/Downloads/WebRTC-D01-certificates/pk_WebRTC-D01.pem",
        "SSLCertPath" : "c:/Users/ankit.sangani/Downloads/WebRTC-D01-certificates/cert_WebRTC-D01.crt",
        "SSLCaPath"   : "c:/SW-AnkitSangani/AWS/sdk/AmazonrootCA.pem"
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
    "cpid": "97FF86E8728645E9B89F7B07977E4B15",
    "sId": "",
    "env": "awspoc",
    "pf": "aws",

    # Camera settings used when streaming is triggered
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
    by the SDK — you do NOT need to handle them here.
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

                # No manual WebRTC start needed!
                # The SDK automatically reads vs.carn from the device sync response
                # and starts the WebRTC MASTER if vs.as=true and vs.carn is set.
                #
                # If vs.as=false, the SDK waits for a ct=112 cloud command.
                # Either way, the firmware doesn't need to do anything for streaming.

                print("Firmware :: Entering telemetry loop...")
                print("Firmware :: WebRTC will auto-start from device sync (vs.as + vs.carn)")
                print("Firmware :: Or wait for ct=112 cloud command")

                while True:
                    sendTelemetry(Sdk)
                    time.sleep(interval)

            except KeyboardInterrupt:
                print("Firmware :: Interrupted")
                Sdk.Dispose()
                sys.exit(0)

    except Exception as ex:
        print(ex)


if __name__ == "__main__":
    main()
