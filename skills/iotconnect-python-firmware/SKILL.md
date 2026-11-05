---
name: iotconnect-python-firmware
description: Build, configure and debug device firmware that uses the Avnet /IOTCONNECT Python SDK (the `iotconnect` package, `IoTConnectSDK` class). Use when writing or fixing a Python app that connects a device to /IOTCONNECT, sends telemetry (D2C) that must match a device template, handles cloud commands, OTA, twin or direct methods (C2D), acknowledges commands, manages gateway/child devices, streams video through AWS Kinesis Video Streams, or uploads files. Also use for connection failures and "my data does not show up" problems.
---

# /IOTCONNECT Python SDK: firmware integration

Help a firmware developer write the application that sits on top of an installed
`iotconnect-sdk` package: configure it, connect, send data to the cloud (D2C) and
react to cloud messages (C2D).

**Scope:** Python firmware only. This skill does not cover SDKs for other languages.
**Version basis:** checked against the SDK source at repository commit 8712097 (the SDK package
files last changed in 9adca10). Where the README and the code disagree, this skill follows the code
(`references/troubleshooting.md`, "Docs versus code"). Behaviour claims are pinned by stub tests
that run the SDK's own code; anything not verified that way is marked unverified.

## Workflow

1. **Collect inputs. Ask for anything missing, never invent values.** Expect the project layout
   (`references/sample-config-map.md`, "Project layout"): when a device is created, its certificates go in
   `certs/<UniqueId>/` (or `certs/` for a single device) and its exported template in `templates/` (or `template/`).
   Check that `certs/` and `iotc.env` are git-ignored before writing anything.
   - Device `uniqueId`, and `cpid` + `env` (or `sId`), `pf` (usually `aws`), discovery URL
   - Authentication: X.509 certificate paths (key, cert, root CA) or a `devicePrimaryKey`
   - The **device template JSON** exported from the platform (preferred). Without it, the attribute names and types
   - Whether the device is a **gateway with children**. If so, read `references/gateway-and-children.md` and start from `assets/gateway_firmware_template.py`
   - Which features are needed: telemetry, commands, OTA, twin, video, file upload
   If the developer already has a sample-style firmware file with these values hard-coded, run
   `scripts/import_sample_config.py FILE` to pull them into an env file instead of retyping.
   Where each value comes from and what to change from the sample: `references/sample-config-map.md`.
   **Write `iotc.env` yourself** in the project folder from the values given (format: `assets/iotc.env.example`),
   with paths relative to the project. Add `iotc.env` and `certs/` to `.gitignore` if missing. Do not echo the
   CPID or keys back in chat. A `devicePrimaryKey` is a secret: ask the developer to type it into the file instead
   of pasting it. The starters and preflight load `iotc.env` automatically, so nobody has to source it.
2. **Start from `assets/firmware_template.py`.** Fill in only what the user needs. Read
   settings from environment variables or a config file, never hardcode paths,
   IDs, ARNs or keys.
   If a template was given, run `scripts/template_tool.py summary` and `skeleton` on it and build the
   readings, commands and twin settings from that output. See "Working from a device template" below.
3. **Run `scripts/preflight.py` yourself** from the project folder before the first connection, fix every FAIL
   you can (wrong path, missing `.gitignore` entry, send interval) and report the rest. It checks Python,
   the package, certificate files, required settings, the template against the settings, and that secrets are
   git-ignored. It finds files in the project layout and prints the `iotc.env` lines for them. It changes nothing.
4. **Implement callbacks** for the cloud messages the firmware must act on (table below).
5. **Send data** following the rules below, then **verify** with the checklist at the end.

## Lifecycle in one view

```python
with IoTConnectSDK(UniqueId, SdkOptions, connection_cb) as Sdk:   # blocks until connected
    Sdk.onDeviceCommand(device_cb)       # C2D: commands (ct 0)
    Sdk.onOTACommand(ota_cb)             # C2D: firmware update (ct 1)
    Sdk.onTwinChangeCommand(twin_cb)     # C2D: desired twin properties
    Sdk.onReady(ready_cb)                # attributes loaded, safe to send data
    Sdk.getTwins()                       # ask for current twin properties
    while running:
        Sdk.SendData([{"uniqueId": UniqueId, "time": utc_now, "data": {...}}])   # D2C
```

## Every firmware must keep these (even for the simplest template)

When you write or trim firmware, from the starters or from scratch, keep all of these. Change only
the parts marked TODO. A test run with another agent dropped the first two, so do not treat them as optional:

1. **Command and OTA handlers stay registered.** Register `onDeviceCommand` and `onOTACommand` and acknowledge
   whatever you do not handle as failed (`sendAckCmd(ack, 1, ...)`, `sendOTAAckCmd(ack, 1, ...)`). Do this
   **even when the template defines no commands**: the platform can still send a command or an OTA, and an
   unacknowledged one stays pending there.
2. **The send interval has a floor in code:** `max(configured interval, template dataFrequency)`. The
   starters read `dataFrequency` from `IOTC_TEMPLATE` and enforce it. Do not replace that with a plain
   `int(os.environ[...])`: a low value in `iotc.env` would make most `SendData` calls return `None`.
3. **Settings come from `iotc.env`.** Keep the starter's `load_env_file()`. Never put IDs, keys or paths in code.
4. **Values match the template types.** For example `int(...)` for INTEGER, even for stub readings.
5. **Wait for `onReady` in the main thread, then pause a second, then send.** Check that the result is `True`.
6. **Catch `IoTConnectSDKException` (print `ex.message`) and `AttributeError`** (a failed discovery request)
   around the constructor.
7. **`.gitignore` covers what the device writes:** `certs/`, `iotc.env`, `__pycache__/` and `logs/`. The SDK
   writes `logs/debug/` (with `IsDebug`) and `logs/offline/` (with offline storage) into the folder of the
   script it runs from, so a `firmware/` folder gets its own `firmware/logs/`.

## Working from a device template

/IOTCONNECT attaches a template to every device and expects the device to send only data in that
format. The template is optional for the developer to supply, but when it is available use it.

```
python3 scripts/template_tool.py summary  TEMPLATE.json
python3 scripts/template_tool.py sample   TEMPLATE.json
python3 scripts/template_tool.py skeleton TEMPLATE.json
python3 scripts/template_tool.py validate TEMPLATE.json payload.json
python3 scripts/preflight.py --template TEMPLATE.json
```

Use it to name every `SendData` key, pick Python types, set the send interval from `dataFrequency`,
match commands on their `command` text and convert twin setting defaults. For debugging, validate the
payload the firmware actually sends. Format, type table and pitfalls: `references/device-template.md`.
Examples of real templates: `assets/example-templates/`.

## Which callback for which cloud message

| Firmware needs to... | Register | Notes |
|---|---|---|
| Run a device command | `onDeviceCommand(cb)` | `cb(msg)`; acknowledge with `sendAckCmd` if `msg["ack"]` is set |
| Apply a firmware update | `onOTACommand(cb)` | acknowledge with `sendOTAAckCmd` |
| React to twin changes | `onTwinChangeCommand(cb)` | report back with `UpdateTwin(key, value)` |
| Know the connection state | 3rd constructor argument | receives `ct` 116 messages |
| Know when attributes are loaded | `onReady(cb)` | wait for it before the first `SendData`; never send from inside it |
| Track a gateway's child list | `onDeviceChangeCommand(cb)` | see `references/gateway-and-children.md` |
| Handle direct methods | `regiter_directmethod_callback(name, cb)` | spelled this way in the SDK |

Full signatures and behaviour: `references/api-reference.md`.

## Rules that prevent the most common failures

1. **Always pass `sdkOptions` containing `cpid` (or `sId`).** The constructor raises if both are blank,
   even though the README calls `sdkOptions` optional.
2. **The constructor blocks** until the device is synced and connected. Wrap it in
   `try/except IoTConnectSDKException` and print `ex.message` (`str(ex)` shows only the raw code tuple).
3. **Do not send faster than the cloud data frequency.** For non-edge devices `SendData`
   silently drops calls that arrive before the window has elapsed and returns `None`.
   Treat only a return value of `True` as sent (`False`: publish failed or no item matched a known device).
4. **Wait for `onReady` in the main thread, then pause about a second.** Before attributes load, `SendData`
   sends nothing. The SDK attaches its validators just after `onReady` returns, so a send made inside the
   callback goes out entirely as FLT.
5. **Data keys must equal the attribute local names in the device template.** Unmatched keys go out
   as a separate FLT message instead of normal telemetry. Group attributes are nested objects.
6. **The device sends only what its template defines.** Types are enforced: INTEGER and LONG need a Python `int` (a float or bool fails),
   DECIMAL a number (text such as `"21.5"` fails), BIT `0` or `1` (not a bool), BOOLEAN a bool, LATLONG a list of two numbers.
   A bad value is sent as FLT and looks like missing data. An OBJECT attribute given a non-dict makes the whole call send nothing.
   Convert twin values to the setting type before `UpdateTwin`: the SDK checks them only when the setting has `dataValidation`.
7. **Timestamps:** UTC, format `YYYY-MM-DDTHH:MM:SS.000Z`.
8. **Acknowledge every command that carries `ack`.** Use `msg["ack"]` as the id and pass `str(msg["id"])` as
   `childId` when present; an unknown or non-string child id makes the SDK send nothing. Do not call the ack
   methods when there is no `ack`. Command status: 2 executed, 1 failed. OTA status: 2 downloading, 3 downloaded,
   4 download failed, **5 success**, 1 failed (the README's `0` for OTA success is wrong).
9. **Do not handle `ct` 112/113 (video start/stop) in your callbacks.** The SDK handles them internally and never delivers them.
10. **Barred, disabled, released or stop commands (106 to 109)** make the SDK disconnect and clear offline
   storage without calling any callback. After that the send methods quietly do nothing.
11. **Never use the SDK after `Dispose()`.** Some methods then raise `IoTConnectSDKException`, but `SendData` and
   `UpdateTwin` just return `None`, so a disposed SDK can look like a quiet one.
12. **Secrets:** keep keys out of source control and logs. `GetCredentials()` returns raw temporary AWS credentials, so do not print them.
13. **TLS:** the SDK constructor switches Python's default HTTPS context to *unverified* unless
    the environment variable `PYTHONHTTPSVERIFY` is set to a non-empty value. Tell the user and
    suggest setting `PYTHONHTTPSVERIFY=1` in production, then testing connectivity.
14. **Turn `IsDebug` off in production.** It prints SDK diagnostics, including message payloads.
15. **Put `keepalive` at the top level of `SdkOptions`.** The SDK sample nests it in `offlineStorage`, where it is ignored.

## Reference files (read only when needed)

| Read this | When |
|---|---|
| `references/api-reference.md` | Exact method signatures, callbacks, return values, gateway/child calls |
| `references/device-template.md` | A template is supplied, or data is missing or lands as FLT, or twin/command setup |
| `references/data-and-commands.md` | Building the telemetry payload, `SendData` return values, command types, acknowledgement statuses |
| `references/gateway-and-children.md` | Gateway devices: tags, one payload for many devices, child commands and OTA |
| `references/sample-config-map.md` | Project layout (`certs/`, `templates/`, `iotc.env`), filling in identity and certificate settings, converting the SDK sample's config, or moving from the sample to real firmware |
| `references/sdk-options.md` | Filling in or debugging `SdkOptions` |
| `references/video-and-file-upload.md` | Kinesis video streaming (PutMedia or WebRTC) or S3 file upload |
| `references/troubleshooting.md` | Any error, silent failure, or install problem |

## Verification checklist

- [ ] `scripts/preflight.py` passes
- [ ] The constructor returns and the connection callback reports connected
- [ ] `onReady` fired before the first send
- [ ] With a template: `template_tool.py validate` reports 0 errors for the real payload (gateway: with `--device UID=TAG` for every device)
- [ ] `SendData` returned `True` and the data is visible in the platform
- [ ] A test command from the platform reaches the callback and is acknowledged (and one for each child type)
- [ ] No keys, certificate paths or account identifiers are hardcoded in the delivered code
- [ ] `certs/`, `iotc.env`, `__pycache__/` and `logs/` are git-ignored, and the downloaded certificate zip is deleted
- [ ] Every item of "Every firmware must keep these" is still in the delivered code
- [ ] `IsDebug` is off for production builds
