# API reference (what firmware calls)

Verified against the SDK source (repository commit 8712097). Behaviours marked *tested* are pinned in
`tests/test_sdk_behaviour.py` of the skill's source repository. `Sdk` below is an `IoTConnectSDK` instance.

## Construction and shutdown

```python
IoTConnectSDK(uniqueId, sdkOptions=None, initCallback=None)
```

- Use it as a context manager (`with ... as Sdk:`). Leaving the block disconnects.
- Raises `IoTConnectSDKException` when `uniqueId` is blank, both `sId` and `cpid` are blank, or
  `discoveryUrl` lacks `http`.
- If the discovery request itself fails (no network, wrong host), the SDK's own error handler fails and
  the caller sees `AttributeError: ... has no attribute 'message'` instead (*tested*). Catch it too, or run
  `scripts/preflight.py --check-network` first.
- **Blocks** until the first cloud message arrives after sync. A device that is not registered,
  active and acquired in the platform, or has bad certificates, can wait here.
- `initCallback(msg)` receives connection-state messages (`ct` 116). `msg["command"]` carries the state;
  the SDK itself compares it as text, so treat it as a string.
- `Sdk.Dispose()` disconnects and clears internal state. Afterwards `getTwins`, `sendAckCmd` and
  `sendOTAAckCmd` raise `IoTConnectSDKException`, but `SendData` and `UpdateTwin` return `None` quietly
  and `Getdevice` returns `None` (*tested*). Do not rely on an exception to notice a disposed SDK.

## Callback registration (all take one function)

| Method | Callback signature | Fires for |
|---|---|---|
| `onDeviceCommand(cb)` | `cb(msg)` | device command, `ct` 0 |
| `onOTACommand(cb)` | `cb(msg)` | firmware update, `ct` 1 |
| `onModuleCommand(cb)` | `cb(msg)` | module command, `ct` 2 |
| `onTwinChangeCommand(cb)` | `cb(msg)`, `msg = {"desired": {...}, "uniqueId": ...}` | desired twin properties |
| `onAttrChangeCommand(cb)` | `cb(msg)` | attribute change, `ct` 101 (the SDK also re-syncs) |
| `onRuleChangeCommand(cb)` | `cb(msg)` | rule change, `ct` 103 (the SDK also re-syncs) |
| `onDeviceChangeCommand(cb)` | `cb(msg)` | device list changed (gateway child list) |
| `onReady(cb)` | `cb(msg)` | attributes loaded (`ct` 201). The SDK attaches its validators just **after** this returns, so do not call `SendData` inside it (*tested*) |
| `regiter_directmethod_callback(name, cb)` | `cb(msg, methodname, requestId)` | direct method named `name` (Azure only: subscribed when `pf` is `az`) |

The misspelling `regiter_directmethod_callback` is the real method name. The registry is a class
attribute, so it is shared by every `IoTConnectSDK` instance in the process (*tested*).

An exception raised inside the twin or direct-method callback is turned into a `TypeError` by the SDK's
own error handler (*tested*). Catch exceptions inside these callbacks yourself.

Callbacks run on SDK threads. Keep them short and thread-safe. Do heavy work (a firmware
download, a long actuator move) on your own worker thread and acknowledge when it finishes.

## Device to cloud

| Method | Purpose | Returns / behaviour |
|---|---|---|
| `SendData(list)` | publish telemetry | `True` sent; `False` failed or nothing matched; `None` not attempted or the payload made the SDK fail. Table in `data-and-commands.md` (*tested*) |
| `UpdateTwin(key, value)` | report a twin property | no return value. Ignored if `key` is not a twin setting. The value is checked only when the setting has `dataValidation` (*tested*) |
| `sendAckCmd(ackGuid, status, msg, childId=None)` | acknowledge a device command | raises if `ackGuid` is `None`. `childId` must be a `str` listed by `Getdevice()`, otherwise nothing is sent (*tested*) |
| `sendOTAAckCmd(ackGuid, status, msg, childId=None)` | acknowledge a firmware command | same rules as `sendAckCmd`; success status is 5 |
| `DirectMethodACK(msg, status, requestId)` | answer a direct method | `status` and `requestId` are converted to strings. SDK bug: the first status used is kept for every later response of that connection (*tested*) |

## Cloud to device (requests)

| Method | Purpose | Notes |
|---|---|---|
| `getTwins()` | request all twin properties | answer arrives via the twin callback |
| `Getdevice()` | list devices (gateway and children) | `None` if not ready or disposed |
| `GetAttributes(callback)` | fetch the attribute list | pass a callback; it receives the list |

## Gateway and child devices (gateway devices only)

Walkthrough, tags and child acknowledgements: `gateway-and-children.md`.

| Method | Purpose | Notes |
|---|---|---|
| `createChildDevice(deviceId, deviceTag, displayName, callback=None)` | create a child | raises `IoTConnectSDKException("04")` on failure. Callback gets `{"status": bool, "message": str}`. Ids with spaces are not rejected (*tested*), so check them yourself |
| `delete_child(child_id, callback)` | delete a child | returns `None`. The callback reports `status: True` even on failure, so read the `message` (*tested*) |

Create-child error messages (callback `message`): 1 missing tag, 2 missing unique id, 3 missing
display name, 4 gateway not found, 5 could not create, 6 invalid tag, 7 tag equals the gateway's,
8 unique id already exists, 9 unique id longer than 128 characters.

## File upload and credentials

See `video-and-file-upload.md`: `UploadImage`, `UploadImageWithClassification`, `GetCredentials`.

## Exceptions

`IoTConnectSDKException` carries a readable `message`; `str(ex)` shows only the raw arguments.

| Code | Meaning |
|---|---|
| 00 | internal error or "you are not able to call this function" (used after `Dispose`) |
| 01 | something missing or blank (config, unique id, SID/CPID, discovery URL) |
| 02 | unable to read the base URL |
| 03 | sync response error |
| 04 | unable to proceed without required info |
| 05 | certificate missing or invalid |
| 06 | protocol initialisation failed |
| 07 | template initialisation failed |
| 08 | tumbling-window initialisation failed |
| 09 | data processing failed |
