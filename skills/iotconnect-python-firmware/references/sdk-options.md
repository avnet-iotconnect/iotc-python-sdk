# SdkOptions reference

`SdkOptions` is a dictionary passed as the second argument of `IoTConnectSDK`. Despite the
README calling it optional, it must supply at least `cpid` (or `sId`), so treat it as required.

## Template

```python
SdkOptions = {
    "certificate": {                       # X.509 devices
        "SSLKeyPath":  "<path to device private key>",
        "SSLCertPath": "<path to device certificate>",
        "SSLCaPath":   "<path to root CA>",
    },
    # "devicePrimaryKey": "<key>",         # symmetric-key devices instead of "certificate"
    "cpid": "<company id>",
    "env":  "<environment>",
    "pf":   "aws",                         # platform; aws unless told otherwise
    # "sId": "<solution id>",              # use sId OR cpid + env
    "discoveryUrl": "https://discovery.iotconnect.io",
    "keepalive": 60,                       # MQTT keepalive, top level
    "offlineStorage": {"disabled": False, "availSpaceInMb": 5, "fileCount": 5},
    "skipValidation": False,
    "IsDebug": False,
    # "CameraOptions": {"deviceport": "/dev/video0",
    #                   "video": {"width": "640", "height": "480", "framerate": "30/1"}},
}
```

## Keys

| Key | Required | Notes |
|---|---|---|
| `cpid` + `env` | one of (`cpid` + `env`) or `sId` | The SDK builds the discovery lookup from them. In the platform: Settings, then Key Vault |
| `sId` | alternative to `cpid` + `env` | when set, it is used instead |
| `pf` | yes in practice | platform, usually `aws` |
| `discoveryUrl` | no | defaults to `https://discovery.iotconnect.io`; if given it must contain `http`. Use the URL that matches the environment (for example the EU discovery host for Azure EU) |
| `certificate` | for X.509 devices | the three paths. The root CA file name must end in `.pem` or the SDK raises ERR[05] (authType 3 excepted). Use forward slashes on Windows and Linux. Files must exist and be readable |
| `devicePrimaryKey` | for symmetric-key devices | from the platform: device, Info tab, Connection Info, Device Connection |
| `keepalive` | no | MQTT keepalive in seconds, default 60. Must be **top level**: the SDK sample puts it inside `offlineStorage`, where it is never read (*tested*) |
| `offlineStorage` | no | enabled only when `disabled`, `availSpaceInMb` and `fileCount` are all present and `disabled` is `False` |
| `skipValidation` | no | `True` turns off template-based validation of values |
| `IsDebug` | no | `True` prints SDK diagnostics, including message payloads. Keep off in production |
| `CameraOptions` | for video | see `video-and-file-upload.md` |

The authentication type (certificate or symmetric key) is a property of the device in the
platform. Supply the matching option.

## Offline storage

- Buffers readings while disconnected and sends them after reconnecting.
- The sample uses `availSpaceInMb: 0.01`, a demonstration value that holds almost nothing.
  Size it for the device's real storage and the expected outage length. The README warns that
  oversized storage can harm the device and stop execution when memory fills.
- A barred, disabled, released or stop command clears the stored files.

## Paths and secrets

- Build paths from environment variables or a config file. Do not commit key files.
- Restrict the private key file to the user that runs the firmware (on Linux, mode 600).
- Never log the contents of `SdkOptions`.
