#!/usr/bin/env python3
"""
Starter firmware for the /IOTCONNECT Python SDK (package `iotconnect`).

Settings come from iotc.env (loaded automatically from the current folder or the project folder)
or from environment variables, so that no keys, paths or IDs live in source code:

  IOTC_UNIQUE_ID       device unique id                         (required)
  IOTC_CPID            company id                               (required unless IOTC_SID is set)
  IOTC_ENV             environment                              (required with IOTC_CPID)
  IOTC_SID             solution id (alternative to CPID + ENV)
  IOTC_PF              platform, default "aws"
  IOTC_DISCOVERY_URL   default https://discovery.iotconnect.io
  IOTC_KEY / IOTC_CERT / IOTC_CA   X.509 key, certificate and root CA paths
  IOTC_PRIMARY_KEY     symmetric key (use instead of the three paths above)
  IOTC_SEND_INTERVAL   seconds between readings; never below the template dataFrequency (enforced)
  IOTC_TEMPLATE        device template JSON; its dataFrequency sets the minimum interval
  IOTC_DEBUG           "1" to print SDK diagnostics (keep off in production)

Search for "TODO" to find what must be replaced before this is real firmware.
"""

import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone

from iotconnect import IoTConnectSDK
from iotconnect.IoTConnectSDKException import IoTConnectSDKException

# --------------------------------------------------------------------------------------
# iotc.env: settings file written by the agent or by scripts/import_sample_config.py.
# Loaded automatically; variables already set in the environment win. Relative paths in the
# file (certs/..., templates/...) are taken relative to the file's folder.
# --------------------------------------------------------------------------------------
_PATH_KEYS = ("IOTC_KEY", "IOTC_CERT", "IOTC_CA", "IOTC_TEMPLATE")


def load_env_file(path=None):
    here = os.path.dirname(os.path.abspath(__file__))
    explicit = path or os.environ.get("IOTC_ENV_FILE")
    candidates = [explicit] if explicit else [
        os.path.join(os.getcwd(), "iotc.env"), os.path.join(here, "iotc.env"),
        os.path.join(os.path.dirname(here), "iotc.env")]
    for p in candidates:
        if not (p and os.path.isfile(p)):
            continue
        base = os.path.dirname(os.path.abspath(p))
        with open(p, encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:].lstrip()
                k, v = (x.strip() for x in line.split("=", 1))
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                    v = v[1:-1].replace("'\\''", "'")
                if k in _PATH_KEYS and v and not os.path.isabs(v):
                    v = os.path.normpath(os.path.join(base, v))
                os.environ.setdefault(k, v)
        return p
    return None


ENV_FILE = load_env_file()


# --------------------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------------------
UNIQUE_ID = os.environ.get("IOTC_UNIQUE_ID", "")
def template_data_frequency():
    """dataFrequency (seconds) of the template named by IOTC_TEMPLATE, or None."""
    path = os.environ.get("IOTC_TEMPLATE")
    if not path:
        return None
    try:
        import json
        with open(path, encoding="utf-8-sig") as fh:
            return int(str((json.load(fh).get("properties") or {}).get("dataFrequency")).strip())
    except (OSError, ValueError, TypeError, AttributeError):
        return None


# Never send faster than the template's dataFrequency: the SDK silently drops calls inside the window
# (SendData returns None). Keep this floor even if you change how SEND_INTERVAL is chosen.
DATA_FREQUENCY = template_data_frequency()
SEND_INTERVAL = int(os.environ.get("IOTC_SEND_INTERVAL", str(DATA_FREQUENCY or 60)))
if DATA_FREQUENCY and SEND_INTERVAL < DATA_FREQUENCY:
    print("IOTC_SEND_INTERVAL {} s is below the template dataFrequency {} s; using {} s".format(
        SEND_INTERVAL, DATA_FREQUENCY, DATA_FREQUENCY))
    SEND_INTERVAL = DATA_FREQUENCY

SDK_OPTIONS = {
    "cpid": os.environ.get("IOTC_CPID", ""),
    "sId": os.environ.get("IOTC_SID", ""),
    "env": os.environ.get("IOTC_ENV", ""),
    "pf": os.environ.get("IOTC_PF", "aws"),
    "discoveryUrl": os.environ.get("IOTC_DISCOVERY_URL", "https://discovery.iotconnect.io"),
    "IsDebug": os.environ.get("IOTC_DEBUG", "0") == "1",
    "skipValidation": False,
    "keepalive": 60,   # MQTT keepalive; must be top level (the SDK never reads it inside offlineStorage)
    # TODO: size the offline buffer for this device's storage and expected outages.
    # All three keys are required, or the SDK leaves offline storage off.
    "offlineStorage": {"disabled": False, "availSpaceInMb": 5, "fileCount": 5},
}

if os.environ.get("IOTC_PRIMARY_KEY"):
    SDK_OPTIONS["devicePrimaryKey"] = os.environ["IOTC_PRIMARY_KEY"]
else:
    SDK_OPTIONS["certificate"] = {
        "SSLKeyPath": os.environ.get("IOTC_KEY", ""),
        "SSLCertPath": os.environ.get("IOTC_CERT", ""),
        "SSLCaPath": os.environ.get("IOTC_CA", ""),
    }

# TODO: only if this device streams video (see references/video-and-file-upload.md):
# SDK_OPTIONS["CameraOptions"] = {"deviceport": "/dev/video0",
#                                 "video": {"width": "640", "height": "480", "framerate": "30/1"}}

# Acknowledgement statuses, from docs.iotconnect.io/sdk/custom/reference-table (device message 2.1).
# The SDK passes them through unchanged. Note OTA success is 5; 0 means "executed (cloud only)".
ACK_CMD_FAILED = 1
ACK_CMD_EXECUTED = 2
OTA_FAILED, OTA_DOWNLOADING, OTA_DOWNLOADED, OTA_DOWNLOAD_FAILED, OTA_SUCCESS = 1, 2, 3, 4, 5

Sdk = None
ready = threading.Event()
stop = threading.Event()


# --------------------------------------------------------------------------------------
# Your device logic (replace these)
# --------------------------------------------------------------------------------------
def read_sensors():
    """Return {attribute local name: value}. Names must match the device template exactly.
    Grouped attributes are nested: {"gyroscope": {"x": 0.1}}."""
    # TODO: replace with real sensor reads. "temperature" is a placeholder name.
    return {"temperature": 0.0}


def handle_command(msg):
    """Run a device command. Return (success, text). Print `msg` once to see the field names."""
    # TODO: implement. Unhandled commands are reported as failed so the platform is not misled.
    return False, "no handler implemented"


def apply_twin(key, value):
    """Apply a desired twin property (already converted). Return True when it was applied."""
    # TODO: implement. Only properties that are twin settings in the template can be reported.
    return False


# Twin settings: {localName: (TYPE, converter)}. Paste the SETTINGS block printed by
# scripts/template_tool.py skeleton TEMPLATE.json. Values arrive as the cloud sent them
# (often text); the SDK checks them only when the setting has dataValidation.
SETTINGS = {}


OTA_SUPPORTED = False  # TODO: set True once you implement download, verify and apply


# --------------------------------------------------------------------------------------
# SDK callbacks. They run on SDK threads, so keep them short.
# --------------------------------------------------------------------------------------
def on_connection(msg):
    # ct 116: connection status. msg["command"] holds the state.
    print("connection:", msg.get("command") if msg else msg)


def on_ready(_msg):
    # Attributes are loaded; it is now safe to send data.
    ready.set()


# KEEP on_device_command and on_ota registered even when the template defines no commands or OTA:
# the platform can still send them, and a command that is never acknowledged stays pending there.
def on_device_command(msg):
    print("command received:", msg)
    ack = msg.get("ack") if msg else None
    ok, text = handle_command(msg)
    if ack:
        Sdk.sendAckCmd(ack, ACK_CMD_EXECUTED if ok else ACK_CMD_FAILED, text, msg.get("id"))


def on_ota(msg):
    print("firmware command received:", msg)
    ack = msg.get("ack") if msg else None
    if not ack:
        return
    if not OTA_SUPPORTED:
        Sdk.sendOTAAckCmd(ack, OTA_FAILED, "OTA not supported by this firmware")
        return
    # TODO: for each entry in msg["urls"]: ack OTA_DOWNLOADING, download, ack OTA_DOWNLOADED
    # (or OTA_DOWNLOAD_FAILED), verify and apply, then ack OTA_SUCCESS or OTA_FAILED.


def on_twin(msg):
    desired = (msg or {}).get("desired") or {}
    for key, value in desired.items():
        if key in ("version", "uniqueId"):
            continue
        _type, convert = SETTINGS.get(key, (None, lambda v: v))
        try:
            value = convert(value)
        except (TypeError, ValueError):
            print("twin: cannot convert", key)
            continue
        if apply_twin(key, value):
            Sdk.UpdateTwin(key, value)


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def main():
    global Sdk
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    try:
        # Blocks until the device is synced and connected.
        with IoTConnectSDK(UNIQUE_ID, SDK_OPTIONS, on_connection) as sdk:
            Sdk = sdk
            sdk.onDeviceCommand(on_device_command)
            sdk.onOTACommand(on_ota)
            sdk.onTwinChangeCommand(on_twin)
            sdk.onReady(on_ready)
            sdk.getTwins()

            if not ready.wait(timeout=60):
                print("warning: attributes not loaded after 60 s; continuing anyway")
            # The SDK calls onReady just before it attaches its validators; a send in that gap
            # goes out as FLT. Never call SendData from inside on_ready.
            time.sleep(1)

            while not stop.is_set():
                payload = [{"uniqueId": UNIQUE_ID, "time": utc_now(), "data": read_sensors()}]
                result = sdk.SendData(payload)
                # True = sent. False = publish failed, or no item matched a known device.
                # None = not attempted (not ready, barred or stopped, inside the data-frequency
                # window, after Dispose) or the payload made the SDK fail (see device-template.md).
                print("SendData ->", result)
                stop.wait(SEND_INTERVAL)
    except IoTConnectSDKException as ex:
        print("SDK error:", ex.message)  # str(ex) shows only the raw code tuple
        return 1
    except AttributeError as ex:         # a failed discovery request surfaces as AttributeError
        print("could not reach the discovery service:", ex)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
