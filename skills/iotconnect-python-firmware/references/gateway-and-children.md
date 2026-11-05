# Gateway and child devices

Read this when the device is a gateway: one connection that reports for itself and for other
devices (children) behind it.

## The model: one template, one tag per device type

/IOTCONNECT does **not** give each child its own template. The gateway's template holds the
attributes of the gateway **and** of every child type, and each attribute carries a **tag**. A child
is created with one of those tags and inherits the gateway's template. It may send only the
attributes of its own tag. The platform docs state this ("Children inherit the gateway's template";
docs.iotconnect.io/device/gateway). The SDK enforces it: when the gateway has children, an attribute
is matched only if its tag equals the sending device's tag (`IoTConnectSDK.py` lines 1202-1206 for
plain attributes, 1233-1237 for objects).

So "a template per child" becomes "a tag per child type" inside the one gateway template:

| Tag | Who sends it | Attributes (example `assets/example-templates/gateway_pumpstation_template.json`) |
|---|---|---|
| `gw` | the gateway itself | `uptime`, `cpu` |
| `pump` | every child created with tag `pump` | `flow`, `running`, `motor {rpm, temp}` |
| `tank` | every child created with tag `tank` | `level` (0 to 100), `alarm` |

The example template was **constructed** for this skill in the export format. It was not exported
from a platform. Use the gateway's real exported template in a project.

## Walkthrough

1. **Get the gateway template** and run
   `python3 scripts/template_tool.py summary GATEWAY.json`. Attributes are listed per tag.
2. **Create the children** in the platform (gateway device, Child Devices tab) or from firmware with
   `createChildDevice(child_id, tag, display_name, callback)`. The tag must be one of the template's tags.
   The SDK re-reads the device list after a successful create (`ct` 221 then `mt` 204).
3. **Generate readers per tag:** `python3 scripts/template_tool.py skeleton GATEWAY.json` prints one
   `read_<tag>()` function per tag and a `READERS_BY_TAG` table.
4. **Start from `assets/gateway_firmware_template.py`.** It builds one `SendData` list from
   `Sdk.Getdevice()`, one item per device id, and picks the reader by the device's tag.
5. **Validate a real payload** with the device-to-tag map:
   `python3 scripts/template_tool.py validate GATEWAY.json payload.json --device gw1=gw --device pump1=pump`.
   Keys of another tag, unknown ids and wrong types are all reported.
6. **Handle commands and OTA for children** (below), then run the checklist in `SKILL.md`.

## Sending data

```python
devices = Sdk.Getdevice()           # [{"tg": "gw", "id": "gw1"}, {"tg": "pump", "id": "pump1"}, ...]
Sdk.SendData([
    {"uniqueId": "gw1",   "time": now, "data": {"uptime": 5}},
    {"uniqueId": "pump1", "time": now, "data": {"flow": 1.5, "running": 1, "motor": {"rpm": 900, "temp": 41.0}}},
])
```

- The gateway's own entry is always first in `Getdevice()` (`IoTConnectSDK.py` 637 and 1014).
- An item whose `uniqueId` is not in `Getdevice()` is skipped silently. If no item matches, `SendData`
  returns `False`, not `None` (tested).
- A key from another tag (for example `level` sent by `pump1`) goes out as FLT (tested).
- Tag matching applies only once the gateway **has** children (`has.d`). A gateway without children
  matches attributes by name alone.

## Commands for a child

Commands for children arrive on the gateway's `onDeviceCommand` callback. When the message names a
child in `id`, acknowledge with that id as `childId`:

```python
def on_device_command(msg):
    child = str(msg["id"]) if msg.get("id") else None
    ok, info = run_command(child or GATEWAY_ID, msg.get("cmd") or msg.get("command"), msg)
    if msg.get("ack"):
        Sdk.sendAckCmd(msg["ack"], 2 if ok else 1, info, child)
```

What the SDK does with `childId` (`IoTConnectSDK.py` 1403-1437, all tested):

| `childId` | Result |
|---|---|
| `None` | ack sent for the gateway, no `cid` |
| a `str` listed in `Getdevice()` | ack sent with `"cid": childId` |
| a `str` not in `Getdevice()` | **nothing is sent**, no error |
| a non-string, for example an `int` | **nothing is sent**, no error |

The command text field: commands raised by edge rules carry it in `command`
(`IoTConnectSDK.command_sender`). The field name in platform-sent commands is not visible in the SDK
code; the starter reads `cmd` and falls back to `command`. Print the first message to confirm.

## OTA for children

An OTA message carries `urls`. Each entry may have a `tg`, meaning "for the devices with this tag".
Send one acknowledgement per target device, with the child id for children:

```python
for entry in msg["urls"]:
    targets = [d["id"] for d in Sdk.Getdevice() if d["tg"] == entry["tg"]] if entry.get("tg") else [None]
    for dev in targets:
        child = None if dev in (None, GATEWAY_ID) else dev
        Sdk.sendOTAAckCmd(msg["ack"], 2, "downloading", child)
        ...
        Sdk.sendOTAAckCmd(msg["ack"], 5, "applied", child)    # 5 = success, 1 = failed
```

`sendOTAAckCmd` follows the same `childId` rules as `sendAckCmd`, and publishes `type` 1 on the
acknowledgement topic (tested). The status values are in `data-and-commands.md`.

## Creating and deleting children: SDK pitfalls

| Call | What to know |
|---|---|
| `createChildDevice(id, tag, name, cb)` | the result arrives in `cb({"status": bool, "message": str})`. The SDK does **not** reject ids with spaces (its check is inverted), so validate ids yourself: no spaces, at most 128 characters |
| `delete_child(id, cb)` | `cb` reports `status: True` even when deletion fails, so read `message`. After a successful delete the SDK does not remove the child from `Getdevice()` until the next device-list refresh. Call it only on a gateway: on other devices it returns `None` without an error |
| `onDeviceChangeCommand(cb)` | fires when the platform sends the new device list (`ct` 204) |

All three behaviours are pinned in `tests/test_sdk_behaviour.py` (`GatewayTests`) in the skill's source repository.
