# Video Streaming & WebRTC Implementation Guide

## Overview

The IoTConnect Python SDK supports two video streaming modes for AWS Kinesis Video Streams (KVS):

1. **WebRTC (peer-to-peer)** — Low-latency, bidirectional streaming via KVS Signaling Channels. The device acts as MASTER; viewers connect as VIEWERs.
2. **PutMedia (GStreamer)** — One-way H.264 video ingestion via `kvssink` GStreamer plugin.

Both modes are managed entirely by the SDK. The firmware developer only needs to provide configuration.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         IoTConnect Cloud                              │
│                                                                      │
│  Device Sync Response (vs object):                                   │
│    vs.url  = credential endpoint URL                                 │
│    vs.as   = true/false (auto-start)                                 │
│    vs.carn = channel ARN (if WebRTC) or empty (if PutMedia)          │
│                                                                      │
│  Cloud Commands:                                                     │
│    ct=112 (stream_start) with webrtc=true/false, carn=<ARN>          │
│    ct=113 (stream_stop)                                              │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ MQTT
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    IoTConnect SDK (IoTConnectSDK.py)                  │
│                                                                      │
│  - Intercepts ct=112 / ct=113 commands                               │
│  - Reads vs object from device sync response                         │
│  - Decides WebRTC vs GStreamer based on webrtc flag / carn presence   │
│  - Manages credential acquisition and subprocess lifecycle           │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌─────────────────────────┐  ┌─────────────────────────────┐
│  WebRTC Path            │  │  GStreamer/PutMedia Path     │
│  (kvsWebRTCClientMaster │  │  (gst-launch-1.0 + kvssink) │
│   .py subprocess)       │  │                             │
└─────────────────────────┘  └─────────────────────────────┘
```

---

## Device Sync Response (VS Object)

When the SDK connects and performs device sync, the cloud returns a `vs` (video stream) object inside `p` (properties):

```json
{
  "p": {
    "vs": {
      "url": "https://<endpoint>.credentials.iot.<region>.amazonaws.com/role-aliases/<alias>/credentials",
      "as": true,
      "carn": "arn:aws:kinesisvideo:<region>:<account>:channel/<channel-name>/<id>"
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `vs.url` | string | AWS IoT Credential Provider endpoint for obtaining temporary AWS credentials |
| `vs.as` | boolean | Auto-start flag. If `true`, streaming starts immediately on device connect |
| `vs.carn` | string | KVS Signaling Channel ARN. If non-empty → WebRTC mode. If empty → PutMedia mode |

---

## Streaming Modes Decision Logic

```
vs.as = true, vs.carn = "<ARN>"     → Auto-start WebRTC MASTER
vs.as = true, vs.carn = ""          → Auto-start GStreamer/PutMedia
vs.as = false                       → Wait for ct=112 cloud command

ct=112 with webrtc=true, carn=<ARN> → Start WebRTC MASTER
ct=112 with webrtc=false (or absent)→ Start GStreamer/PutMedia
ct=113                              → Stop any active stream
```

---

## WebRTC Flow (Detailed)

### 1. Credential Acquisition

The SDK calls the IoT Credential Provider endpoint using the device's X.509 certificate to obtain temporary AWS credentials:

```
GET https://<endpoint>.credentials.iot.<region>.amazonaws.com/role-aliases/<alias>/credentials
Headers: x-amzn-iot-thingname: <device-uid>
TLS Client Cert: device certificate + private key
CA: Amazon Root CA
```

Response:
```json
{
  "credentials": {
    "accessKeyId": "ASIA...",
    "secretAccessKey": "...",
    "sessionToken": "...",
    "expiration": "2025-..."
  }
}
```

**Implementation:** `awskinesisclient.py → get_kinesis_cer()`

### 2. Subprocess Launch

The SDK launches `kvsWebRTCClientMaster.py` as a subprocess with credentials injected via environment variables:

```
AWS_ACCESS_KEY_ID=<accessKeyId>
AWS_SECRET_ACCESS_KEY=<secretAccessKey>
AWS_SESSION_TOKEN=<sessionToken>
AWS_DEFAULT_REGION=<region extracted from channel ARN>
```

**Implementation:** `awskinesisclient.py → start_kvs_webrtc_from_devicecert()`

### 3. Signaling Channel Connection

The WebRTC MASTER client:
1. Gets signaling channel endpoints (HTTPS + WSS) from KVS API
2. Fetches ICE server configuration (STUN + TURN servers)
3. Signs the WSS URL using SigV4 authentication
4. Connects to the signaling channel WebSocket as MASTER

**Implementation:** `kvsWebRTCClientMaster.py → KinesisVideoClient`

### 4. Peer Connection (Viewer Connects)

When a viewer connects:
1. Viewer sends an **SDP Offer** via the signaling channel
2. MASTER creates an `RTCPeerConnection` with ICE servers
3. MASTER adds video/audio tracks from the camera
4. MASTER generates an **SDP Answer** and sends it back
5. Both sides exchange **ICE Candidates** for NAT traversal
6. Media flows directly between MASTER and VIEWER (peer-to-peer)

### 5. Media Capture

The `MediaTrackManager` class handles platform-specific camera access:

| Platform | Video Source | Format |
|----------|-------------|--------|
| Linux | `/dev/video0` | v4l2 |
| macOS | `default:default` | avfoundation |
| Windows | `Integrated Camera` | dshow |

Default resolution: 1280x720 @ 30fps (configurable via `CameraOptions`)

---

## GStreamer/PutMedia Flow

When WebRTC is not used (no `carn` or `webrtc=false`):

1. SDK obtains temporary credentials (same as WebRTC flow)
2. Builds a GStreamer pipeline:
   - **Video:** `v4l2src → videoconvert → x264enc → kvssink`
   - **Audio (if mic detected):** `alsasrc → audioconvert → voaacenc → kvssink`
3. Launches `gst-launch-1.0` as a subprocess
4. Video is ingested into a KVS stream (viewable via HLS/DASH, not peer-to-peer)

**Implementation:** `awskinesisclient.py → start_gstreamer()`

---

## Cloud Commands

### Start Streaming (ct=112)

```json
{
  "v": "2.1",
  "ct": 112,
  "webrtc": true,
  "carn": "arn:aws:kinesisvideo:us-east-1:123456789:channel/MyChannel/1234567890"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `ct` | Yes | Command type 112 (stream_start) |
| `webrtc` | No | `true` for WebRTC, `false`/absent for GStreamer |
| `carn` | Conditional | Required when `webrtc=true`. The KVS signaling channel ARN |

### Stop Streaming (ct=113)

```json
{
  "v": "2.1",
  "ct": 113
}
```

Stops any active stream (WebRTC or GStreamer).

---

## Firmware Implementation

The firmware only needs to configure the SDK. No streaming code is required:

```python
import sys
import json
import time
from iotconnect import IoTConnectSDK
from datetime import datetime, timezone

UniqueId = "your-device-unique-id"

SdkOptions = {
    "certificate": {
        "SSLKeyPath"  : "/path/to/device_private_key.pem",
        "SSLCertPath" : "/path/to/device_certificate.crt",
        "SSLCaPath"   : "/path/to/AmazonRootCA1.pem"
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
    "cpid": "your-cpid",
    "sId": "",
    "env": "your-env",
    "pf": "aws",
    "CameraOptions": {
        "deviceport": "/dev/video0",
        "video": {
            "width": "640",
            "height": "480",
            "framerate": "30/1"
        }
    }
}

def DeviceCallback(msg):
    # ct=112/113 are handled by SDK internally
    # Only ct=0 (device commands) reach here
    print("Command received:", json.dumps(msg))

def DeviceConnectionCallback(msg):
    print("Connection status:", json.dumps(msg))

def main():
    with IoTConnectSDK(UniqueId, SdkOptions, DeviceConnectionCallback) as Sdk:
        Sdk.onDeviceCommand(DeviceCallback)
        # SDK auto-starts WebRTC from device sync (vs.as + vs.carn)
        # Or waits for ct=112 cloud command
        while True:
            # Send telemetry
            time.sleep(10)

if __name__ == "__main__":
    main()
```

---

## SDK Options Reference

### CameraOptions

```json
{
  "CameraOptions": {
    "deviceport": "/dev/video0",
    "video": {
      "width": "640",
      "height": "480",
      "framerate": "30/1"
    }
  }
}
```

| Field | Description |
|-------|-------------|
| `deviceport` | Video device path. Auto-detected if not set (Linux only) |
| `video.width` | Video width in pixels |
| `video.height` | Video height in pixels |
| `video.framerate` | Frame rate (GStreamer format, e.g., "30/1") |

### Certificate Options

```json
{
  "certificate": {
    "SSLKeyPath": "/path/to/private_key.pem",
    "SSLCertPath": "/path/to/certificate.crt",
    "SSLCaPath": "/path/to/AmazonRootCA1.pem"
  }
}
```

These certificates are used for:
1. MQTT connection to IoTConnect
2. Obtaining temporary AWS credentials from the IoT Credential Provider
3. Passed to the WebRTC subprocess for credential acquisition

---

## Dependencies

### Required Python Packages (for WebRTC)

```
boto3
aiortc
websockets
requests
python-dotenv
```

### System Dependencies (for GStreamer/PutMedia)

```
gstreamer1.0
gstreamer1.0-plugins-base
gstreamer1.0-plugins-good
gstreamer1.0-plugins-bad
gstreamer1.0-plugins-ugly
x264
Amazon Kinesis Video Streams Producer SDK (kvssink plugin)
```

### Installation on Raspberry Pi / Debian

```bash
# For WebRTC mode
pip3 install --break-system-packages boto3 aiortc websockets requests python-dotenv

# For GStreamer mode (PutMedia)
apt install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-x264
# Plus KVS Producer SDK with kvssink (build from source)
```

---

## File Structure

```
iotconnect-sdk-1.0/
└── iotconnect/
    ├── IoTConnectSDK.py              # Main SDK - intercepts ct=112/113, manages vs object
    └── client/
        ├── awskinesisclient.py       # Credential acquisition, subprocess management
        │   ├── get_kinesis_cer()     # Gets temp AWS creds via device cert
        │   ├── start_kvs_webrtc_from_devicecert()  # Launches WebRTC MASTER
        │   ├── start_gstreamer()     # Launches GStreamer pipeline
        │   └── stop_gstreamer()      # Stops active stream
        └── kvsWebRTCClientMaster.py  # WebRTC MASTER client (runs as subprocess)
            ├── KinesisVideoClient    # Signaling, ICE, peer connections
            ├── MediaTrackManager     # Camera/media capture
            └── IoTCredentialProvider # Alternative credential fetch (standalone mode)

sample-webrtc/
├── iotconnect-sdk-1.0-firmware-python_webrtc.py  # Firmware sample
├── iotconnect-sdk-1.0.tar.gz                     # SDK package
└── requirements-webrtc.txt                        # Python dependencies
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: No module named 'boto3'` | Dependencies not installed for the correct Python | Install with `/usr/bin/python -m pip install boto3 aiortc ...` |
| `KVS WebRTC master client exited immediately with code 1` | Missing dependency or bad credentials | Check subprocess stderr logs (KVMERR prefix) |
| Viewer shows loader, no video | MASTER not connected to signaling channel | Verify device logs show "Signaling Server Connected!" |
| `InvalidStateError: invalid state` in logs | Known aioice race condition (cosmetic) | Harmless — does not affect streaming |
| ICE stays at "checking" | Firewall blocking UDP/TURN | Ensure TURN server ports (443) are accessible |
| `webrtc requested but carn not provided` | ct=112 sent without carn field | Include `carn` in the cloud command payload |
| Credentials fetch fails (non-200) | Wrong role alias or thing name mismatch | Verify IoT policy allows credential provider access |
| No video device found | Camera not connected or wrong device path | Set `CameraOptions.deviceport` explicitly |

---

## Viewer Side (React UI)

The IoTConnect cloud API returns everything the viewer needs:

```json
{
  "webRtcDetails": {
    "channelARN": "arn:aws:kinesisvideo:...",
    "wssEndpoint": "wss://...",
    "httpsEndpoint": "https://...",
    "viewerCredentials": {
      "accessKeyId": "...",
      "secretAccessKey": "...",
      "sessionToken": "..."
    },
    "iceServers": [...]
  }
}
```

The React viewer must:
1. Sign the `wssEndpoint` URL with SigV4 using `viewerCredentials` (service: `kinesisvideo`)
2. Connect to the signed WSS URL as a **VIEWER** (include `X-Amz-ClientId` param)
3. Create an `RTCPeerConnection` with the provided `iceServers`
4. Send an **SDP Offer** through the signaling channel
5. Receive the **SDP Answer** from the MASTER
6. Exchange ICE candidates
7. Attach the remote stream to a `<video autoplay muted>` element

**Important:** The `<video>` element must have `autoplay` and `muted` attributes or browsers will block playback.
