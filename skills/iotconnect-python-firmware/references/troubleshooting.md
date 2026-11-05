# Troubleshooting

Turn `IsDebug` on while diagnosing. Many failures are silent by design: methods return quietly
when the device is not started, and only the debug output says why.

## Install

| Symptom | Cause | Fix |
|---|---|---|
| `pip install` of the SDK fails on macOS, asking for `pypiwin32` | `setup.py` tests `'win' in sys.platform`, and `"darwin"` contains `"win"` | install on Linux or Windows, or remove the `pypiwin32` requirement from `setup.py` for a local macOS test |
| Syntax or import errors on an old Python | `setup.py` says `>=3.5`, but the code uses f-strings | use Python 3.6 or newer (3.11 or newer is safest). Ignore the README's Python 2.7 and 3.5 claims |
| WebRTC import errors (`aiortc`, `websockets`, `boto3`) | those packages are not in the SDK's requirements | `pip install -r requirements-webrtc.txt` |

## Connecting

| Symptom | Likely cause | What to check |
|---|---|---|
| `AttributeError: ... has no attribute 'message'` while creating the SDK object | the discovery request failed and the SDK's error handler itself fails | network, DNS or proxy; `discoveryUrl`; `cpid`, `env`, `pf` values. Request the discovery URL manually |
| `SDK ERR[01]: SID / CPID can not be blank` | `sdkOptions` missing or has no `cpid` / `sId` | pass `sdkOptions` with `cpid` (or `sId`) |
| `SDK ERR[05]` certificate missing or invalid | wrong path, unreadable file, wrong file for the device | the three paths exist and belong to this device |
| `SDK ERR[05]` although the files exist | the root CA file name does not end in `.pem` (the SDK checks the name; authType 3 is exempt) | rename or copy the file to `.pem` |
| `SDK ERR[02]` unable to read base URL | listed in the SDK but not reachable in this version: a failed lookup raises the `AttributeError` above instead | check the same items as for the `AttributeError` |
| Constructor never returns | waiting for the first cloud message after sync | device registered, active and acquired in the platform; certificates match; system clock correct |
| `print(ex)` shows `('01', '...')` | the exception keeps raw arguments | print `ex.message` |

## Data is not arriving

Check in this order:

1. `SendData` returned `True`? If `None`, see 2 to 4 and 9. If `False`, the publish failed or no item's `uniqueId` is a known device (5).
2. Called before `onReady`, or from inside the `onReady` callback? Wait for it in the main thread, then pause a second.
3. Sending faster than the data frequency? Calls inside the window are dropped silently. Send at the configured interval.
4. Did the platform bar, disable, release or stop the device (`ct` 106 to 109)? The SDK has disconnected; check the device status in the platform.
5. Is `uniqueId` in `Getdevice()`? Unknown ids are ignored.
6. Do the keys equal the template attribute local names? Unmatched keys go out as FLT, not as normal telemetry.
7. Any call after `Dispose()`? It raises.
8. Are the value types right for the template? An INTEGER sent as `21.5` or `True`, a DECIMAL sent as the text `"21.5"`, a BIT sent as `True`, a BOOLEAN sent as `1` or a DATETIME without the literal `.000Z` goes out as FLT. Run `scripts/template_tool.py validate TEMPLATE payload.json`.
9. Does the call fail outright (`None` every time)? A non-dict for an OBJECT attribute, a missing `uniqueId`/`time`/`data`, or a STRING `dataValidation` containing a value with `to` in it (`stop`, `auto`) makes the SDK send nothing. `validate` reports these as FATAL.
10. Gateway: is each key an attribute of the sending device's tag? See `gateway-and-children.md`.

## Commands and twin

| Symptom | Cause | Fix |
|---|---|---|
| Command stays pending in the platform | no acknowledgement sent | call `sendAckCmd` with `msg["ack"]` |
| `sendAckCmd` raises `ackGuid not valid` | called for a command without `ack` | guard with `if msg.get("ack")` |
| Ack for a child does nothing | `childId` not in the device list, or not a string | pass `str(msg["id"])`; check `Getdevice()` |
| `UpdateTwin` has no effect | key is not a template setting, or the setting has `dataValidation` and the value fails it (text `"0"` for a BIT) | use the setting `localName`; convert to the declared type first (`template_tool.py skeleton` shows how) |
| Reported twin value has the wrong type on the platform | the setting has no `dataValidation`, so the SDK sent the text as given | convert before `UpdateTwin` |
| Twin or direct-method callback raises `TypeError` | your callback raised; the SDK's error handler concatenates the exception to a string | catch exceptions inside the callback |
| Direct-method responses all carry the first status | SDK bug in `mqttclient.SendDirectData` | until fixed, use one status, or reconnect |
| Callback for a direct method never runs | method name not registered | `regiter_directmethod_callback(name, cb)` before the call arrives |
| Video start/stop not seen in `DeviceCallback` | `ct` 112 and 113 are handled internally | do not wait for them in callbacks |

## Video

| Symptom | Check |
|---|---|
| Stream does not start | `ct` 112 for WebRTC includes both `webrtc: true` and `carn`; certificate paths valid; the credential endpoint was delivered at sync |
| `kvssink` not found | `gst-inspect-1.0 kvssink`; set `GST_PLUGIN_PATH` to the folder containing `libgstkvssink.so` |
| Camera not found | `ls /dev/video*`; add the user to the `video` group; test with `gst-launch-1.0 v4l2src device=/dev/video0 ! videoconvert ! autovideosink` |
| Credential errors | certificate permissions, role alias permissions in AWS, device clock |
| WebRTC stops after about an hour | credentials expire; the watchdog should restart it; look for the restart message in the log |
| Quality or bandwidth problems | lower resolution or frame rate; use hardware H.264 encoding if available |

## Harmless noise

- `rtp:` and `flt:` lines printed on every `SendData` are expected.
- `Video_Stream_Task : ...` lines are the SDK reporting stream state.

## Docs versus code

When these disagree, trust the code.

| README or sample says | Code does |
|---|---|
| `sdkOptions` optional | needs `cpid` or `sId` from it |
| `Sdk.GetAllTwins()` | no such method; use `getTwins()` |
| `GetAttributes()` with no arguments | `GetAttributes(callback)` |
| handle `ct` 112 / 113 in `DeviceCallback` | never delivered to callbacks |
| OTA success status 0 (README) | 5 is success in the platform table; 0 is "executed (cloud only)". The SDK passes the value through |
| `ct` 116 to 121 for template, rule and device changes (platform reference table) | the SDK uses 101 to 109 for those and 116 for its own connection-status message |
| `keepalive` inside `offlineStorage` (sample) | read only at top level |
| Python 2.7, 3.5 and 3.7 to 3.13 supported | f-strings are used, so 3.6 or newer; `setup.py` lists 3.6 to 3.11 |
| ack status comments `st = 6` / `st = 4` | out of date; the SDK passes your status through |
