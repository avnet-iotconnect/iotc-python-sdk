# Device templates

A device template is the JSON contract between the device and /IOTCONNECT. It is created in the
platform and attached to the device. The device is expected to send only the data the template
defines, in the types it defines. Anything else is not treated as normal telemetry.

Examples in `assets/example-templates/`: `A040626011_template.json` and `A21Nov2501_template.json` are
real exports; `gateway_pumpstation_template.json` was constructed for this skill (see
`gateway-and-children.md`). A project uses the template attached to its own device.

## Ask for the template first

Prefer the exported template JSON over attribute names typed by hand. Then run:

```
python3 scripts/template_tool.py summary  TEMPLATE.json     # what the template defines, per tag
python3 scripts/template_tool.py sample   TEMPLATE.json     # a payload the SDK sends as RPT
python3 scripts/template_tool.py skeleton TEMPLATE.json     # starter code for readings, commands, twin
python3 scripts/template_tool.py validate TEMPLATE.json payload.json   # or - for stdin
python3 scripts/template_tool.py validate GATEWAY.json payload.json --device gw1=gw --device pump1=pump
```

All are read-only and use only the standard library. `validate` exits 1 when any value would not go
out as RPT, and 2 on unreadable input. Without a template, ask the developer for names and types.

`summary` warns when the file is the platform's template **reference** (placeholder types such as
`"number | string"`), not an export, and when a `dataValidation` would make the SDK fail.

## What the template contains

| Template field | Meaning for firmware |
|---|---|
| `attributes[]` (`name`, `type`, `childs`, `tag`, `dataValidation`) | telemetry. `name` is the key in `SendData` `data` |
| `attributes[].type == "OBJECT"` | send a dict whose keys are the `childs[].name` |
| `attributes[].tag` | gateway templates: which device type sends the attribute |
| `settings[]` (`localName`, `type`, `defaultValue`, `isReadOnly`, `dataValidation`) | twin properties. Report with `UpdateTwin(localName, value)`. `defaultValue` is always text. Greengrass-style files call the list `shadow` |
| `commands[]` (`name`, `command`, `requiredParam`, `requiredAck`, `isOTACommand`, `tag`) | cloud commands. The device receives the `command` text, not `name`. Flags may be text (`"false"`) in some files |
| `directMethods[]` | Azure only: the SDK subscribes to direct methods only when `pf` is `az` (`mqttclient.py` line 79) |
| `properties.dataFrequency` | seconds between sends, as text. Faster calls send nothing |
| `properties.fileSupport` | whether file upload is configured |
| `properties.videoStream*`, `autoStartVideoStream` | video settings (see `video-and-file-upload.md`) |
| `authType` | 2, 3 and 7 need certificates. 5 needs a `devicePrimaryKey` |
| `messageVersion` | this SDK speaks `2.1` |

## Value rules the SDK enforces

A value that fails its rule is not discarded. It is sent as FLT (a fault message) instead of
normal telemetry (RPT), so the data appears missing on dashboards. Every row below is covered by a
differential test: `template_tool.py` and the SDK's own code must agree on more than 150 cases.

| Type | Send this in Python | Goes to FLT |
|---|---|---|
| INTEGER | `int`, within plus or minus 2**31 | a float (`21.5`, even `21.0`), a **bool**, text with a `.` |
| LONG | `int`, within plus or minus 2**63 | same as INTEGER |
| DECIMAL | `int` or `float` | **text with a decimal point** (`"21.5"`: the SDK only parses whole-number text) |
| STRING | `str` | a number |
| DATETIME | `"YYYY-MM-DDTHH:MM:SS.000Z"` | `isoformat()` output, or any other fraction than the literal `.000Z` |
| DATE | `"YYYY-MM-DD"` | other orders |
| TIME | `"HH:MM:SS"` | `"HH:MM"` |
| BIT | `int` 0 or 1 | `True`/`False` (unless a `dataValidation` list is set, see below) |
| BOOLEAN | `bool` | `0` and `1` |
| LATLONG | list of exactly 2 numbers | a tuple, a dict, three values |
| ARRAY | list | a tuple |
| OBJECT | dict of the child attributes | **anything else makes the whole `SendData` call fail and return `None`** |

Build the DATETIME text with `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")`.

### `dataValidation`

When an attribute has a `dataValidation`, the SDK checks it (it arrives as `dv` in the sync reply).
The format is comma-separated values or `AtoB` ranges:

| Type | Example | Effect |
|---|---|---|
| INTEGER, LONG, DECIMAL | `0to100`, `1,2,5` | value must be in a range or equal a listed value |
| STRING | `red,green` | value must equal a listed value |
| BIT | `0,1` | value must equal a listed number. Here `True` and `1.0` are accepted |
| BOOLEAN | `true,false` | `1` and `0` are accepted too |
| ARRAY | `1to3` | list **length** must be in range |
| DATE, TIME, DATETIME | anything | never rejects a well-formed value (the SDK's range check cannot fail) |

**SDK bug:** in a STRING `dataValidation`, any allowed value that contains the letters `to` (`stop`,
`auto`, `toggle`) is parsed as a numeric range and makes `SendData` fail for the whole message.
`summary` warns about it; until the SDK is fixed, rename those values in the template.

## Gotchas seen in real templates

- **Same name flat and nested.** A template can define `ppint` both at top level and inside the object
  `ppobj` (`A21Nov2501`). Send `"ppint": 1` for one and `"ppobj": {"ppint": 1}` for the other.
- **Attributes are optional per message.** A subset is fine. Keys not in the template are the problem.
- **Names are case-sensitive.** `humidity` is not `Humidity`.
- **Setting defaults are text.** `"defaultValue": "0"` for a BIT setting must become `0` before
  `UpdateTwin`. The SDK checks the value only if the setting has `dataValidation`; otherwise it sends
  the text as given. The `skeleton` command prints the conversions.
- **Commands match on `command`, not `name`.** In `A21Nov2501` the command named `RR_ON` arrives as `rru_on`.
- **`requiredAck`.** Acknowledge when the message carries `ack`, whatever the flag says.
- **`dataFrequency` is text** (`"60"`). Convert it before using it as a sleep time.
- **A changed template.** The SDK re-syncs when the platform signals an attribute change (`ct` 101).
  If new attributes still do not show up, restart the firmware.

## Debugging data with a template

1. Run `summary` and confirm the names and types the firmware must use (per tag for a gateway).
2. Dump the payload the firmware sends (print it once) and pass it to `validate`. For a gateway, add
   `--device UID=TAG` for every device in the payload.
3. `ERROR` lines go out as FLT; `FATAL` lines make the SDK send nothing from that call. Fix the type
   in code, not in the template, unless the template itself is wrong.
4. A key reported as "not an attribute" is misspelled, belongs inside an OBJECT, belongs to another
   tag, or is missing from the template.
5. If `validate` is clean and data still does not arrive, continue with `troubleshooting.md`.

## Limits of the checker

`template_tool.py` mirrors `common/data_evaluation.py` and `common/util.py` of the SDK (checked at
repository commit 8712097) for non-edge devices. It does not model edge aggregation. It does not contact the
platform, so it cannot tell whether the template is the one attached to the device. It assumes the
template's `type`, `tag` and `dataValidation` arrive as the SDK's `dt`, `tg` and `dv`. That mapping
follows from the field names; it was not checked against a captured sync reply.
