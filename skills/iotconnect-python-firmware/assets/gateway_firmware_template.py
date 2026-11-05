#!/usr/bin/env python3
"""
Starter firmware for an /IOTCONNECT gateway with child devices (package `iotconnect`).

How gateways work in this SDK (see references/gateway-and-children.md):
  * One gateway template covers the gateway and every child. Each attribute carries a tag;
    a child is created with one of those tags and may send only the attributes of its tag.
  * The gateway sends everyone's readings in one SendData list, one item per device uniqueId.
  * Commands and OTA for a child arrive on the gateway's callbacks; acknowledge them with the
    child's id as a string, or the SDK sends nothing.

Settings come from iotc.env (loaded automatically) or the same IOTC_* environment variables as
firmware_template.py.
Search for "TODO" to find what must be replaced.
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

UNIQUE_ID = os.environ.get("IOTC_UNIQUE_ID", "")          # the gateway's own unique id
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
    "keepalive": 60,                                       # top level; the SDK ignores it inside offlineStorage
    "offlineStorage": {"disabled": False, "availSpaceInMb": 5, "fileCount": 5},   # TODO: size for the device
    "certificate": {
        "SSLKeyPath": os.environ.get("IOTC_KEY", ""),
        "SSLCertPath": os.environ.get("IOTC_CERT", ""),
        "SSLCaPath": os.environ.get("IOTC_CA", ""),
    },
}

# Acknowledgement statuses (docs.iotconnect.io/sdk/custom/reference-table, device message 2.1).
ACK_CMD_FAILED, ACK_CMD_EXECUTED = 1, 2
OTA_FAILED, OTA_DOWNLOADING, OTA_DOWNLOADED, OTA_DOWNLOAD_FAILED, OTA_SUCCESS = 1, 2, 3, 4, 5

Sdk = None
ready = threading.Event()
stop = threading.Event()


# --------------------------------------------------------------------------------------
# Your device logic: one reader per tag in the gateway template (TODO: replace)
# Generate these with: scripts/template_tool.py skeleton GATEWAY_TEMPLATE.json
# --------------------------------------------------------------------------------------
def read_gateway():
    return {"uptime": int(time.monotonic())}


def read_pump(child_id):
    return {"flow": 0.0, "running": 0, "motor": {"rpm": 0, "temp": 0.0}}


def read_tank(child_id):
    return {"level": 0, "alarm": False}


READERS_BY_TAG = {"pump": read_pump, "tank": read_tank}   # TODO: one entry per child tag


def run_command(device_id, text, msg):
    """Run a command for the gateway or one child. Return (success, message)."""
    # TODO: implement. Unknown commands are reported as failed so the platform is not misled.
    return False, "no handler for {!r}".format(text)


def apply_firmware(urls_for_device, device_id):
    """Download, verify and apply firmware. Return True on success."""
    return False   # TODO


# --------------------------------------------------------------------------------------
# Building the telemetry list
# --------------------------------------------------------------------------------------
def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def build_payload(devices, now=None):
    """One SendData item per known device. `devices` is Sdk.Getdevice(): [{"id": ..., "tg": ...}].

    The first entry is the gateway itself. Children whose tag has no reader are left out, because
    a key that is not an attribute of the child's tag is sent as FLT.
    """
    now = now or utc_now()
    items = []
    for d in devices or []:
        if d["id"] == UNIQUE_ID:
            data = read_gateway()
        elif d.get("tg") in READERS_BY_TAG:
            data = READERS_BY_TAG[d["tg"]](d["id"])
        else:
            continue
        items.append({"uniqueId": d["id"], "time": now, "data": data})
    return items


# --------------------------------------------------------------------------------------
# Callbacks (SDK threads: keep them short)
# --------------------------------------------------------------------------------------
def target_of(msg):
    """The device a command is for: the child id when the message carries one, else the gateway."""
    cid = msg.get("id")
    return str(cid) if cid else None


def on_device_command(msg):
    print("command received:", msg)               # print once to learn your platform's field names
    child = target_of(msg)
    # Platform commands are expected to carry the text in "cmd" (unverified against this SDK's code);
    # commands raised by edge rules carry it in "command" (IoTConnectSDK.command_sender).
    text = msg.get("cmd") or msg.get("command") or ""
    ok, info = run_command(child or UNIQUE_ID, text, msg)
    if msg.get("ack"):
        # childId must be a str that Getdevice() lists, or the SDK silently sends nothing.
        Sdk.sendAckCmd(msg["ack"], ACK_CMD_EXECUTED if ok else ACK_CMD_FAILED, info, child)


def on_ota(msg):
    """OTA for the gateway and/or children. Each url entry may name a tag ("tg")."""
    print("firmware command received:", msg)
    ack = msg.get("ack")
    if not ack:
        return
    devices = Sdk.Getdevice() or []
    for entry in msg.get("urls") or []:
        tag = entry.get("tg")
        targets = [d["id"] for d in devices if tag and d.get("tg") == tag] if tag else [None]
        for device_id in targets:
            child = None if device_id in (None, UNIQUE_ID) else device_id
            Sdk.sendOTAAckCmd(ack, OTA_DOWNLOADING, "downloading", child)
            ok = apply_firmware(entry, device_id or UNIQUE_ID)
            Sdk.sendOTAAckCmd(ack, OTA_SUCCESS if ok else OTA_FAILED, "applied" if ok else "failed", child)


def on_device_change(msg):
    print("device list changed:", msg)            # ct 204: children added or removed


def on_ready(_msg):
    ready.set()


def on_connection(msg):
    print("connection:", (msg or {}).get("command"))


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
def main():
    global Sdk
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        with IoTConnectSDK(UNIQUE_ID, SDK_OPTIONS, on_connection) as sdk:
            Sdk = sdk
            sdk.onDeviceCommand(on_device_command)
            sdk.onOTACommand(on_ota)
            sdk.onDeviceChangeCommand(on_device_change)
            sdk.onReady(on_ready)
            if not ready.wait(timeout=60):
                print("warning: attributes not loaded after 60 s")
            time.sleep(1)   # the SDK attaches its validators just after onReady returns
            while not stop.is_set():
                result = sdk.SendData(build_payload(sdk.Getdevice()))
                print("SendData ->", result)   # True sent, False failed or nothing matched, None not attempted
                stop.wait(SEND_INTERVAL)
    except IoTConnectSDKException as ex:
        print("SDK error:", ex.message)
        return 1
    except AttributeError as ex:              # a failed discovery request surfaces as AttributeError
        print("could not reach the discovery service:", ex)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
