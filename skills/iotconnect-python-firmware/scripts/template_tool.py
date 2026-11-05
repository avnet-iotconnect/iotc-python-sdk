#!/usr/bin/env python3
"""
Work with an /IOTCONNECT device template (the JSON exported from the platform).

A device only sends valid telemetry when it follows the template attached to it, so this tool
reads the template and helps write and debug firmware against it. It is read-only and uses only
the standard library.

  template_tool.py summary  TEMPLATE.json
  template_tool.py sample   TEMPLATE.json [--uid ID] [--format json|python]
  template_tool.py validate TEMPLATE.json PAYLOAD.json|-  [--device UID=TAG ...] [--tag TAG] [--verbose]
  template_tool.py skeleton TEMPLATE.json

The value rules mirror iotconnect/common/data_evaluation.py and common/util.py of the Python SDK
(non-edge devices, validation on). A value can end three ways:
  RPT    normal telemetry
  FLT    sent as a fault message instead; it looks like missing data on dashboards
  FATAL  the SDK raises inside SendData, which then returns None and sends nothing from that call

Gateway templates give each attribute a tag. With --device UID=TAG the checker applies the SDK's
tag matching: an item for a device is checked only against attributes carrying that device's tag.

Exit status: 0 when every value would go out as RPT, 1 when any would not, 2 on bad input.
"""

import argparse
import json
import pprint
import re
import sys
from datetime import datetime, timezone

DT_FMT = "%Y-%m-%dT%H:%M:%S.000Z"   # the SDK needs the literal ".000Z" for DATETIME values
KNOWN = ("INTEGER", "LONG", "DECIMAL", "STRING", "DATETIME", "DATE", "TIME", "BIT", "BOOLEAN",
         "LATLONG", "ARRAY", "OBJECT")

# How the SDK treats the authentication type number (IoTConnectSDK.py init_protocol).
AUTH = {
    2: "certificate: key, certificate and root CA file",
    3: "certificate, self-signed: key and certificate (root CA optional)",
    5: "symmetric key: devicePrimaryKey",
    7: "certificate: key, certificate and root CA file",
}

HINT = {
    "INTEGER": "int, -2**31..2**31 (float or bool goes to FLT)",
    "LONG": "int, -2**63..2**63 (float or bool goes to FLT)",
    "DECIMAL": "int or float (text with a '.' goes to FLT)",
    "STRING": "str",
    "DATETIME": 'str "YYYY-MM-DDTHH:MM:SS.000Z" (literal .000Z)',
    "DATE": 'str "YYYY-MM-DD"',
    "TIME": 'str "HH:MM:SS"',
    "BIT": "int 0 or 1 (not True/False)",
    "BOOLEAN": "bool True/False (not 0/1)",
    "LATLONG": "list of exactly 2 numbers",
    "ARRAY": "list",
    "OBJECT": "dict of its child attributes (anything else makes SendData fail)",
}


def die(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(2)


# ----------------------------------------------------------------------------- loading
def load_json(path):
    try:
        if path == "-":
            raw = sys.stdin.read()
        else:
            with open(path, encoding="utf-8-sig") as fh:
                raw = fh.read()
        return json.loads(raw)
    except (OSError, ValueError) as ex:
        die("cannot read {}: {}".format(path, ex))


def load_template(path):
    t = load_json(path)
    if not isinstance(t, dict) or not isinstance(t.get("attributes"), list):
        die("{} is not a device template (no 'attributes' list)".format(path))
    for i, a in enumerate(t["attributes"]):
        if not isinstance(a, dict) or not a.get("name"):
            die("{}: attribute {} has no name".format(path, i))
    return t


def as_bool(v):
    """Template flags are bools in exports, but text ("true", "false") in some reference files."""
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v)


def as_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def ttype(a):
    return str(a.get("type", "")).strip().upper()


def tag_of(a):
    return str(a.get("tag") or "")


def dv_of(a):
    v = a.get("dataValidation")
    return "" if v is None else str(v)


def settings_of(t):
    """Exports use 'settings'; the Greengrass reference format calls the same list 'shadow'."""
    if isinstance(t.get("settings"), list):
        return t["settings"], "settings"
    if isinstance(t.get("shadow"), list):
        return t["shadow"], "shadow"
    return [], "settings"


def is_reference_format(t):
    """The platform's import reference files use placeholders such as "number | string"."""
    texts = [t.get("authType"), t.get("messageVersion")] + [a.get("type") for a in t["attributes"]]
    return any(isinstance(x, str) and "|" in x for x in texts)


def has_tags(t):
    return any(tag_of(a) for a in t["attributes"])


# ----------------------------------------------------------------------------- SDK mirror
def _parse_num(x, sign):
    """util.parseNum. Note type(x) == int is False for bool, so True becomes float 1.0."""
    try:
        if type(x) == str:
            if sign and "." in x:
                return float(x)
            return int(x)
        if type(x) == int:
            return int(x)
        return float(x)
    except ValueError:
        return x


def _parse_data(value, sign):
    """util.parseData"""
    try:
        if value is not None:
            if type(value) == str:
                value = value.rstrip()
        else:
            value = ""
        return _parse_num(value, sign)
    except Exception:
        return value


def _time_ok(v, fmt):
    if type(v) != str:
        return False
    try:
        datetime.strptime(v, fmt)
        return True
    except ValueError:
        return False


def _numeric_dv(value, dv, conv):
    ok = False
    for v in dv.split(","):
        if v.find("to") > -1:
            r = v.split("to")
            if value >= conv(r[0]) and value <= conv(r[1]):
                ok = True
        elif conv(value) == conv(v):
            ok = True
    return ok


def _is_valid(t, v, dv):
    """data_evaluation.process_data, validation branch. May raise, like the SDK does."""
    has_dv = dv is not None and dv != ""
    if t in ("INTEGER", "LONG"):
        value = _parse_data(v, 1)
        if isinstance(value, int) and t == "INTEGER" and -(2 ** 31) <= value <= 2 ** 31:
            return _numeric_dv(value, dv, float) if has_dv else True
        if isinstance(value, int) and t == "LONG" and -(2 ** 63) <= value <= 2 ** 63:
            return _numeric_dv(value, dv, int) if has_dv else True
        return False
    if t == "STRING":
        ok = type(v) == str
        if isinstance(v, str) and has_dv:
            ok = False
            for x in dv.split(","):
                if x.find("to") > -1:
                    r = x.split("to")
                    if v >= int(r[0].strip()) and v <= int(r[1].strip()):   # always raises: str vs int
                        ok = True
                elif str(v) == x.strip():
                    ok = True
        return ok
    if t == "DECIMAL":
        value = _parse_data(v, 0)
        if isinstance(value, (int, float)):
            return _numeric_dv(value, dv, float) if has_dv else True
        return False
    if t in ("DATETIME", "DATE", "TIME"):
        # A dataValidation range or value never turns a well-formed value invalid in the SDK.
        return _time_ok(v, {"DATETIME": DT_FMT, "DATE": "%Y-%m-%d", "TIME": "%H:%M:%S"}[t])
    if t == "BIT":
        ok = type(v) == int and (v == 0 or v == 1)
        if has_dv:
            ok = False
            for x in dv.split(","):
                if v == int(x):
                    ok = True
        return ok
    if t == "BOOLEAN":
        ok = type(v) == bool
        if has_dv:
            ok = False
            for x in dv.split(","):
                if x in ("true", "True"):
                    x = True
                elif x in ("false", "False"):
                    x = False
                try:
                    if v == bool(x):
                        ok = True
                except Exception:
                    ok = False
        return ok
    if t == "LATLONG":
        return v is not None and type(v) == list and len(v) == 2
    if t == "ARRAY":
        if v is not None and type(v) == list:
            ok = True
            if has_dv:
                ok = False
                for x in dv.split(","):
                    if x.find("to") > -1:
                        r = x.split("to")
                        if int(r[0]) <= len(v) <= int(r[1]):
                            ok = True
                    elif len(v) == int(x):
                        ok = True
            return ok
        return False
    return False


def sdk_verdict(t, v, dv=""):
    """'RPT', 'FLT' or 'FATAL' for one value of template type t, as the SDK decides it."""
    try:
        return "RPT" if _is_valid((t or "").upper(), v, dv) else "FLT"
    except Exception:
        return "FATAL"


def check_value(t, v, dv=""):
    """Return (status, message). status: ok, warn, error (FLT), fatal (SendData sends nothing), skip."""
    t = (t or "").upper()
    if v is None:
        return "skip", "None is skipped (not sent)"
    if t not in KNOWN:
        return "warn", "type {!r} is not known to this tool; the SDK sends it as FLT if it has no rule for it".format(t)
    verdict = sdk_verdict(t, v, dv)
    rule = " (dataValidation {!r})".format(dv) if dv else ""
    if verdict == "FATAL":
        if t == "STRING" and "to" in dv:
            return "fatal", ("dataValidation {!r} has an entry containing 'to', which the SDK parses as a numeric "
                             "range and fails on; fix the template's allowed values").format(dv)
        return "fatal", "the SDK raises while checking {!r} against{}".format(v, rule or " its rule")
    if verdict == "RPT":
        if isinstance(v, str) and t in ("INTEGER", "LONG", "DECIMAL"):
            return "warn", "numeric text is accepted; send a number"
        if isinstance(v, bool) and t in ("DECIMAL", "BIT"):
            return "warn", "a bool is accepted here{}; send {}".format(rule, "a number" if t == "DECIMAL" else "0 or 1")
        if t == "BOOLEAN" and not isinstance(v, bool):
            return "warn", "accepted only because of dataValidation {!r}; send True/False".format(dv)
        if t == "LATLONG" and not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
            return "warn", "the SDK checks only the length; send two numbers (latitude, longitude)"
        return "ok", ""
    # FLT
    if t in ("INTEGER", "LONG"):
        if isinstance(v, bool):
            return "error", "{} got a bool; the SDK turns it into 1.0, not an int. Send int(value)".format(t)
        n = _parse_data(v, 1)
        if isinstance(n, float):
            return "error", "{} needs a whole number, got {!r}; send int(value) or change the type to DECIMAL".format(t, v)
        if isinstance(n, int):
            return "error", "{!r} is outside the allowed values{}".format(v, rule or " (32/64-bit range)")
        return "error", "{} needs an int, got {}".format(t, type(v).__name__)
    if t == "DECIMAL":
        if isinstance(v, str):
            return "error", "DECIMAL text {!r} is not converted (the SDK only parses whole-number text); send float(value)".format(v)
        if isinstance(v, (int, float)):
            return "error", "{!r} is outside the allowed values{}".format(v, rule)
        return "error", "DECIMAL needs a number, got {}".format(type(v).__name__)
    if t == "STRING":
        if isinstance(v, str):
            return "error", "{!r} is not one of the allowed values{}".format(v, rule)
        return "error", "STRING needs str, got {}".format(type(v).__name__)
    if t == "DATETIME":
        return "error", 'DATETIME needs "YYYY-MM-DDTHH:MM:SS.000Z" (the .000Z is literal), got {!r}'.format(v)
    if t == "DATE":
        return "error", 'DATE needs "YYYY-MM-DD", got {!r}'.format(v)
    if t == "TIME":
        return "error", 'TIME needs "HH:MM:SS", got {!r}'.format(v)
    if t == "BIT":
        return "error", "BIT needs int 0 or 1, got {!r}{}".format(v, rule)
    if t == "BOOLEAN":
        return "error", "BOOLEAN needs True/False, got {!r}{}".format(v, rule)
    if t == "LATLONG":
        return "error", "LATLONG needs a list of exactly 2 numbers, got {!r}".format(v)
    if t == "ARRAY":
        return "error", "ARRAY needs a list{}, got {!r}".format(" of an allowed length" + rule if dv else "", v)
    return "error", "rejected by the SDK"


# ----------------------------------------------------------------------------- validation
def validate_data(tpl, data, tag=None):
    """Return a list of (status, path, message) for one `data` object.

    tag=None: no tag matching (a non-gateway device, or a gateway without children).
    tag="x": gateway with children; only attributes tagged "x" match, as in IoTConnectSDK.SendData.
    """
    if not isinstance(data, dict):
        return [("fatal", "data", "'data' must be a dict of attribute values; the SDK calls data.keys() and fails")]
    attrs = [a for a in tpl["attributes"] if tag is None or tag_of(a) == tag]
    others = {a["name"]: tag_of(a) for a in tpl["attributes"] if a not in attrs}
    flat = {a["name"]: a for a in attrs if ttype(a) != "OBJECT"}
    objs = {a["name"]: a for a in attrs if ttype(a) == "OBJECT"}
    out = []
    for key, val in data.items():
        if key in objs:
            a = objs[key]
            if not isinstance(val, dict):
                out.append(("fatal", key, "OBJECT attribute needs a dict of its child attributes; any other value makes SendData fail"))
                continue
            kids = {c.get("name"): c for c in a.get("childs", []) or []}
            for ck, cv in val.items():
                c = kids.get(ck)
                path = "{}.{}".format(key, ck)
                if c is None:
                    out.append(("error", path, "not a child of {} in the template".format(key)))
                else:
                    st, msg = check_value(ttype(c), cv, dv_of(c))
                    out.append((st, path, msg))
        elif key in flat:
            a = flat[key]
            st, msg = check_value(ttype(a), val, dv_of(a))
            out.append((st, key, msg))
        else:
            if val is None:
                continue
            if key in others:
                out.append(("error", key, "belongs to tag {!r}, not to this device's tag {!r}".format(others[key], tag)))
            else:
                out.append(("error", key, "not an attribute in the template (names are case-sensitive)"))
    return out


def extract_items(obj):
    """Return (items, wrapped). wrapped is True when the input was a bare data object."""
    if isinstance(obj, list):
        return obj, False
    if isinstance(obj, dict) and "data" in obj:
        return [obj], False
    if isinstance(obj, dict):
        return [{"data": obj}], True
    die("payload must be a SendData list, one item, or a data object")


def parse_devices(pairs):
    out = {}
    for p in pairs or []:
        if "=" not in p:
            die("--device needs UID=TAG, got {!r}".format(p))
        uid, tag = p.split("=", 1)
        out[uid] = tag
    return out


def cmd_validate(a):
    t = load_template(a.template)
    items, wrapped = extract_items(load_json(a.payload))
    devices = parse_devices(a.device)
    errors = warns = 0
    if has_tags(t) and not devices and a.tag is None:
        print("info: the template uses tags (gateway). Pass --device UID=TAG for each device in the payload to "
              "check tag matching; checking every key against all tags for now.")

    def report(label, st, path, msg):
        nonlocal errors, warns
        if st in ("error", "fatal"):
            errors += 1
            tail = "  -> sent as FLT, not normal telemetry" if st == "error" else "  -> SendData returns None; nothing in this call is sent"
            print("[{}] {} {}: {}{}".format(label, "ERROR" if st == "error" else "FATAL", path, msg, tail))
        elif st == "warn":
            warns += 1
            print("[{}] warn  {}: {}".format(label, path, msg))
        elif st == "skip":
            print("[{}] skip  {}: {}".format(label, path, msg))
        elif a.verbose:
            print("[{}] ok    {}".format(label, path))

    for i, item in enumerate(items):
        label = "item {}".format(i)
        if not isinstance(item, dict):
            report(label, "fatal", "item", "each item must be a dict with uniqueId, time and data")
            continue
        if not wrapped:
            missing = [k for k in ("uniqueId", "time", "data") if k not in item]
            if missing:
                report(label, "fatal", ",".join(missing), "missing key; SendData reads it directly and fails")
                continue
            if not _time_ok(item["time"], DT_FMT):
                report(label, "warn", "time", '{!r} is not "YYYY-MM-DDTHH:MM:SS.000Z" (UTC); the SDK does not check it, but use this format'.format(item["time"]))
        tag = a.tag
        uid = item.get("uniqueId")
        if devices:
            if uid not in devices:
                report(label, "error", "uniqueId", "{!r} is not in --device; the SDK skips items whose uniqueId it does not know (Getdevice())".format(uid))
                continue
            tag = devices[uid]
            label = "{} {}".format(label, uid)
        for st, path, msg in validate_data(t, item.get("data"), tag):
            report(label, st, path, msg)
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        expected = [x["name"] for x in t["attributes"] if tag is None or tag_of(x) == tag]
        absent = [n for n in expected if n not in data]
        if absent:
            print("[{}] info: {} template attribute(s) not in this payload (allowed): {}".format(label, len(absent), ", ".join(absent)))
    print("\n{} error(s), {} warning(s)".format(errors, warns))
    return 1 if errors else 0


# ----------------------------------------------------------------------------- summary
def cmd_summary(a):
    t = load_template(a.template)
    p = t.get("properties") or {}
    if is_reference_format(t):
        print("NOTE: this looks like a template reference/import file (placeholder types such as 'number | string'),\n"
              "      not a template exported from a device. Export the device's real template and use that.\n")
    print("Template : {} (code {})".format(t.get("name"), t.get("code")))
    mv = t.get("messageVersion")
    print("Message version: {}{}".format(mv, "" if str(mv) == "2.1" else "   <-- this SDK speaks 2.1"))
    at = as_int(t.get("authType"))
    print("Auth type: {} -> {}".format(t.get("authType"), AUTH.get(at, "not specially handled by the SDK; confirm in the platform docs")))
    freq = p.get("dataFrequency")
    print("Data frequency: {}".format(
        "{} s (send no faster than this; extra SendData calls return None and send nothing)".format(as_int(freq))
        if as_int(freq) else "{!r} (not a number)".format(freq)))
    print("File support: {}".format(p.get("fileSupport")))
    vid = {k: v for k, v in p.items() if k.lower().startswith("video") or k == "autoStartVideoStream"}
    if vid:
        print("Video settings: {}".format(json.dumps(vid)))
    if as_bool(t.get("isEdgeSupport")) or as_bool(t.get("isIotEdgeEnable")):
        print("Edge: yes. Edge devices aggregate values on the device; this tool models non-edge sending only.")
    if as_bool(t.get("greenGrass")):
        print("Greengrass template: this skill covers the plain Python SDK, not the Greengrass SDK.")

    tags = sorted({tag_of(x) for x in t["attributes"]})
    print("\nAttributes (send these names exactly):")
    for tg in tags:
        if len(tags) > 1 or tg:
            print("  [tag {!r}]{}".format(tg, "  <- one device type in a gateway; children with this tag send these" if tg else ""))
        for at_ in [x for x in t["attributes"] if tag_of(x) == tg]:
            print("  {:<14} {:<9} {}{}".format(at_["name"], ttype(at_), HINT.get(ttype(at_), "unknown type"), _dv_note(at_)))
            for c in at_.get("childs", []) or []:
                print("    .{:<12} {:<9} {}{}".format(c.get("name"), ttype(c), HINT.get(ttype(c), "unknown type"), _dv_note(c)))
    names = {}
    for at_ in t["attributes"]:
        names.setdefault((tag_of(at_), at_["name"]), []).append("top level")
        for c in at_.get("childs", []) or []:
            names.setdefault((tag_of(at_), c.get("name")), []).append("inside " + str(at_["name"]))
    for (tg, n), w in names.items():
        if len(w) > 1:
            print("  note: '{}' appears {}. Send it flat for the top-level attribute and nested for the child.".format(n, " and ".join(w)))

    sets, key = settings_of(t)
    print("\nSettings (twin properties; report with UpdateTwin using the local name){}:".format(
        "" if key == "settings" else " [read from 'shadow']"))
    for s in sets:
        dv = dv_of(s)
        print("  {:<14} {:<9} default={!r} readOnly={} {}".format(
            s.get("localName") or s.get("name"), str(s.get("type", "")).upper(), s.get("defaultValue"),
            as_bool(s.get("isReadOnly")),
            "allowed={!r}: UpdateTwin drops values that fail it".format(dv) if dv else
            "no dataValidation: UpdateTwin sends any value unchecked, so convert it yourself"))
    if not sets:
        print("  none")

    cmds = t.get("commands") or []
    print("\nCommands (the device receives the `command` text, not the name):")
    for c in cmds:
        flags = []
        if as_bool(c.get("requiredParam")):
            flags.append("takes a parameter")
        if as_bool(c.get("requiredAck")):
            flags.append("must be acknowledged")
        if as_bool(c.get("isOTACommand")):
            flags.append("OTA: arrives in onOTACommand")
        if tag_of(c):
            flags.append("for tag {!r}".format(tag_of(c)))
        print("  {:<14} name={:<10} {}".format(repr(c.get("command")), c.get("name"), ", ".join(flags)))
    if not cmds:
        print("  none")
    dms = t.get("directMethods") or []
    if dms:
        print("\nDirect methods (register with regiter_directmethod_callback; the SDK subscribes to them only when pf is 'az'):")
        for d in dms:
            print("  {!r} timeout={}".format(d.get("methodName"), d.get("responseTimeout")))
    if p.get("fileSupport") is False:
        print("\nnote: fileSupport is false, so UploadImage will probably report that no file-storage configuration was received.")
    for at_ in t["attributes"]:
        for x in [at_] + list(at_.get("childs", []) or []):
            if ttype(x) == "STRING" and "to" in dv_of(x):
                print("\nWARNING: {!r} has dataValidation {!r}. An allowed value containing 'to' makes the SDK fail "
                      "inside SendData for every message that includes this attribute.".format(x.get("name"), dv_of(x)))


def _dv_note(a):
    dv = dv_of(a)
    return "  allowed: {}".format(dv) if dv else ""


# ----------------------------------------------------------------------------- sample
CANDIDATES = {
    "INTEGER": [25, 0, 1], "LONG": [1234567890123, 0, 1], "DECIMAL": [21.5, 0, 1], "STRING": ["sample"],
    "BIT": [1, 0], "BOOLEAN": [True, False], "LATLONG": [[51.5074, -0.1278]], "ARRAY": [[]],
}


def sample_value(a, now):
    t = ttype(a)
    if t == "OBJECT":
        return {c.get("name"): sample_value(c, now) for c in a.get("childs", []) or []}
    if t == "DATETIME":
        return now.strftime(DT_FMT)
    if t == "DATE":
        return now.strftime("%Y-%m-%d")
    if t == "TIME":
        return now.strftime("%H:%M:%S")
    dv = dv_of(a)
    cands = list(CANDIDATES.get(t, [None]))
    if dv:
        for part in dv.split(","):
            part = part.strip()
            lo = part.split("to")[0].strip() if "to" in part else part
            for conv in (int, float):
                try:
                    n = conv(lo)
                    cands.insert(0, [0] * int(n) if t == "ARRAY" else n)   # ARRAY rules are lengths
                    break
                except ValueError:
                    pass
            if t == "STRING":
                cands.insert(0, part)
    for c in cands:
        if sdk_verdict(t, c, dv) == "RPT":
            return c
    return cands[-1] if cands else None


def cmd_sample(a):
    t = load_template(a.template)
    now = datetime.now(timezone.utc)
    tags = sorted({tag_of(x) for x in t["attributes"]}) if has_tags(t) else [None]
    payload = []
    for tg in tags:
        uid = a.uid if tg is None else "<uniqueId of the device with tag {}>".format(tg)
        payload.append({
            "uniqueId": uid,
            "time": now.strftime(DT_FMT),
            "data": {x["name"]: sample_value(x, now) for x in t["attributes"] if tg is None or tag_of(x) == tg},
        })
    if a.format == "python":
        print(pprint.pformat(payload, width=100, sort_dicts=False))
    else:
        print(json.dumps(payload, indent=2))


# ----------------------------------------------------------------------------- skeleton
COERCE = {
    "BIT": 'lambda v: int(str(v).strip().lower() in ("1", "true"))',
    "BOOLEAN": 'lambda v: str(v).strip().lower() in ("1", "true")',
    "INTEGER": "lambda v: int(float(v))",
    "LONG": "lambda v: int(float(v))",
    "DECIMAL": "float",
    "STRING": "str",
    "DATE": "str",
    "TIME": "str",
    "DATETIME": "str",
}


def py_value(a, now, indent):
    pad = " " * indent
    if ttype(a) == "OBJECT":
        lines = ["{"]
        for c in a.get("childs", []) or []:
            lines.append("{}    {!r}: {},  # {}".format(pad, c.get("name"), py_value(c, now, indent + 4), ttype(c)))
        lines.append(pad + "}")
        return "\n".join(lines)
    return repr(sample_value(a, now))


def _ident(text):
    s = re.sub(r"\W", "_", str(text)).strip("_") or "untagged"
    return ("t_" + s) if s[0].isdigit() else s


def cmd_skeleton(a):
    t = load_template(a.template)
    p = t.get("properties") or {}
    now = datetime.now(timezone.utc)
    freq = as_int(p.get("dataFrequency"))
    print("# Generated from template {!r} (code {!r}, message version {!r})".format(t.get("name"), t.get("code"), t.get("messageVersion")))
    print("# Replace every sample value with a real reading; keep the names and types.\n")
    if freq:
        print("SEND_INTERVAL = {}   # template dataFrequency; sending faster drops data\n".format(freq))
    else:
        print("SEND_INTERVAL = 60   # template dataFrequency {!r} is not a number; set this to the real value\n".format(p.get("dataFrequency")))
    tags = sorted({tag_of(x) for x in t["attributes"]}) if has_tags(t) else [None]
    for tg in tags:
        fn = "read_sensors" if tg is None else "read_" + _ident(tg)
        if tg is not None:
            print("# Readings for devices with tag {!r}. Send them with that device's uniqueId.".format(tg))
        print("def {}():".format(fn))
        print("    return {")
        for x in t["attributes"]:
            if tg is None or tag_of(x) == tg:
                print("        {!r}: {},  # {}".format(x["name"], py_value(x, now, 8), HINT.get(ttype(x), ttype(x) or "unknown type")))
        print("    }\n")
    if tags != [None]:
        print("READERS_BY_TAG = {")
        for tg in tags:
            print("    {!r}: read_{},".format(tg, _ident(tg)))
        print("}  # build SendData items as {'uniqueId': d['id'], 'time': ..., 'data': READERS_BY_TAG[d['tg']]()} for d in Sdk.Getdevice()\n")

    cmds = t.get("commands") or []
    print("# Commands the platform can send (match on the `command` text).")
    print("COMMANDS = {")
    for c in cmds:
        print("    {!r}: {{'name': {!r}, 'takes_param': {}, 'must_ack': {}, 'ota': {}, 'tag': {!r}}},".format(
            c.get("command"), c.get("name"), as_bool(c.get("requiredParam")), as_bool(c.get("requiredAck")),
            as_bool(c.get("isOTACommand")), tag_of(c)))
    print("}\n")

    sets, _ = settings_of(t)
    print("# Twin settings: convert the cloud value to the declared type before UpdateTwin.")
    print("# The SDK checks the value only when the setting has dataValidation; otherwise it sends it as given.")
    print("SETTINGS = {")
    for s in sets:
        ty = str(s.get("type", "")).upper()
        print("    {!r}: ({!r}, {}),".format(s.get("localName") or s.get("name"), ty, COERCE.get(ty, "lambda v: v")))
    print("}")


# ----------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only helper for /IOTCONNECT device templates.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("summary", help="show what the template defines")
    s.add_argument("template")
    s.set_defaults(fn=cmd_summary)

    s = sub.add_parser("sample", help="print a SendData-ready payload with valid example values")
    s.add_argument("template")
    s.add_argument("--uid", default="<device-unique-id>")
    s.add_argument("--format", choices=("json", "python"), default="json")
    s.set_defaults(fn=cmd_sample)

    s = sub.add_parser("validate", help="check a payload against the template (use - for stdin)")
    s.add_argument("template")
    s.add_argument("payload")
    s.add_argument("--device", action="append", metavar="UID=TAG",
                   help="gateway: the tag of each device in the payload (repeat per device)")
    s.add_argument("--tag", help="check a single data object against the attributes of this tag")
    s.add_argument("--verbose", action="store_true", help="also list values that are fine")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("skeleton", help="print Python starter code for readings, commands and twin settings")
    s.add_argument("template")
    s.set_defaults(fn=cmd_skeleton)

    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
