#!/usr/bin/env python3
"""
Read the configuration block of an existing /IOTCONNECT Python firmware file (such as the SDK's
sample/iotconnect-sdk-1.0-firmware-python_msg-2_1.py) and write it out as an environment file that
assets/firmware_template.py and scripts/preflight.py understand.

The firmware file is parsed, never run. Only module-level literal values are read: `UniqueId`,
`interval`, `SdkOptions`, and the identity variables some older samples keep outside SdkOptions
(`cpid`, `env`, `sId`/`SId`, `pf`). No SDK import, network call or device access happens.

  import_sample_config.py FIRMWARE.py                 # print the env file with secrets masked
  import_sample_config.py FIRMWARE.py -o iotc.env     # write it (owner-only on Linux/macOS)
  import_sample_config.py FIRMWARE.py --report        # list what was found and what looks wrong

Put iotc.env in the project folder: the firmware starters and preflight.py load it automatically.

Exit status: 0 on success, 2 when the file or its configuration cannot be read.
"""

import argparse
import ast
import os
import re
import sys

WANTED = ("UniqueId", "interval", "SdkOptions", "cpid", "env", "sId", "SId", "pf")
PLACEHOLDER = re.compile(r"<<|>>|^\s*enter\b|^\s*your\b|\byour[ _-]|^\s*$|xxxx", re.I)


def die(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(2)


def read_assignments(path):
    """Return (found, sdk_calls). found maps a wanted name to its literal value, or to the marker
    NOT_LITERAL when the name is assigned something that is not a literal."""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError, UnicodeDecodeError) as ex:
        die("cannot parse {}: {}".format(path, ex))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for tgt in targets:
            if isinstance(tgt, ast.Name) and tgt.id in WANTED:
                try:
                    found[tgt.id] = ast.literal_eval(value)
                except (ValueError, TypeError, SyntaxError, RecursionError):
                    found[tgt.id] = NOT_LITERAL
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == "IoTConnectSDK":
                calls.append((node.lineno, len(node.args) + len(node.keywords)))
    return found, calls


class _NotLiteral:
    def __repr__(self):
        return "<not a literal>"


NOT_LITERAL = _NotLiteral()


def _dict(v):
    return v if isinstance(v, dict) else {}


def _text(v):
    return None if v is NOT_LITERAL or v is None or isinstance(v, (dict, list)) else str(v)


def quote(v):
    return "'" + str(v).replace("'", "'\\''") + "'"


def build(found):
    opts = _dict(found.get("SdkOptions"))
    cert = _dict(opts.get("certificate"))
    sid = opts.get("sId") or found.get("sId") or found.get("SId")
    rows = [
        ("IOTC_UNIQUE_ID", found.get("UniqueId"), False),
        ("IOTC_CPID", opts.get("cpid") or found.get("cpid"), False),
        ("IOTC_ENV", opts.get("env") or found.get("env"), False),
        ("IOTC_SID", sid, False),
        ("IOTC_PF", opts.get("pf") or found.get("pf"), False),
        ("IOTC_DISCOVERY_URL", opts.get("discoveryUrl"), False),
        ("IOTC_KEY", cert.get("SSLKeyPath"), False),
        ("IOTC_CERT", cert.get("SSLCertPath"), False),
        ("IOTC_CA", cert.get("SSLCaPath"), False),
        ("IOTC_PRIMARY_KEY", opts.get("devicePrimaryKey"), True),
        ("IOTC_SEND_INTERVAL", found.get("interval"), False),
    ]
    return [(k, _text(v), secret) for k, v, secret in rows if _text(v) not in (None, "")]


def is_placeholder(v):
    return bool(v) and bool(PLACEHOLDER.search(str(v)))


def problems(found, rows, calls):
    out = []
    raw = found.get("SdkOptions")
    if raw is NOT_LITERAL:
        out.append("SdkOptions is built at run time (not a literal), so its values cannot be read from the file; "
                   "if it already reads environment variables, keep that")
    elif "SdkOptions" in found and not isinstance(raw, dict):
        out.append("SdkOptions is a {}, not a dictionary; the SDK expects a dict".format(type(raw).__name__))
    opts = _dict(raw)
    d = dict((k, v) for k, v, _ in rows)

    for lineno, nargs in calls:
        if nargs > 3:
            out.append("line {}: IoTConnectSDK(...) is called with {} arguments. This SDK's constructor is "
                       "IoTConnectSDK(uniqueId, sdkOptions, initCallback); the file targets an older or different SDK. "
                       "Move cpid/env/sId/pf into SdkOptions".format(lineno, nargs))
    moved = [n for n in ("cpid", "env", "sId", "SId", "pf") if _text(found.get(n)) and not opts.get(n.replace("SId", "sId"))]
    if moved:
        out.append("{} defined outside SdkOptions; this SDK reads them only from SdkOptions (copied into the env file)".format(
            ", ".join(moved)))

    uid = d.get("IOTC_UNIQUE_ID")
    if not uid:
        out.append("UniqueId not found as a literal string")
    elif is_placeholder(uid):
        out.append("UniqueId {!r} is a placeholder; use the device's unique id from the platform".format(uid))
    if not d.get("IOTC_CPID") and not d.get("IOTC_SID"):
        out.append("neither cpid nor sId is set; the SDK raises ERR[01]")
    for k in ("IOTC_CPID", "IOTC_ENV"):
        if is_placeholder(d.get(k)):
            out.append("{} {!r} is a placeholder; take it from the platform (Settings, Key Vault)".format(k, d[k]))
    if d.get("IOTC_CPID") and not d.get("IOTC_ENV") and not d.get("IOTC_SID"):
        out.append("cpid is set without env; the discovery lookup needs both")
    if opts.get("devicePrimaryKey") and opts.get("certificate"):
        out.append("both devicePrimaryKey and certificate are set; use the one that matches the device's auth type")
    if "certificate" in opts and not isinstance(opts["certificate"], dict) and opts["certificate"] is not None:
        out.append("certificate must be a dict with SSLKeyPath, SSLCertPath and SSLCaPath, not a {}".format(
            type(opts["certificate"]).__name__))
    if not opts.get("devicePrimaryKey") and not d.get("IOTC_KEY"):
        out.append("no certificate paths and no devicePrimaryKey; the device cannot authenticate")
    ca = d.get("IOTC_CA", "")
    if ca and not is_placeholder(ca) and not ca.lower().endswith(".pem"):
        out.append("root CA file name does not end in .pem; the SDK raises ERR[05] for it (authType 3 excepted)")
    for k in ("IOTC_KEY", "IOTC_CERT", "IOTC_CA"):
        v = d.get(k, "")
        if not v:
            continue
        if is_placeholder(v):
            out.append("{} is a placeholder ({!r}), not a path".format(k, v))
        elif not os.path.isfile(v):
            hint = ""
            if os.name == "nt" and v.startswith("/mnt/"):
                hint = " (a WSL path; on Windows use the C:/ form, or run the firmware inside WSL)"
            elif os.name != "nt" and re.match(r"^[A-Za-z]:[/\\]", v):
                hint = " (a Windows path)"
            out.append("{} does not exist on this machine{}; set the path on the device that runs the firmware".format(k, hint))
    url = d.get("IOTC_DISCOVERY_URL", "")
    if url and "http" not in url:
        out.append("discoveryUrl does not contain http; the SDK raises ERR[01]")
    if opts.get("IsDebug") is True:
        out.append("IsDebug is True in the source; the SDK prints payloads. Keep it off in production (IOTC_DEBUG=0)")
    off = opts.get("offlineStorage")
    if isinstance(off, dict):
        missing = [k for k in ("disabled", "availSpaceInMb", "fileCount") if k not in off]
        if missing:
            out.append("offlineStorage lacks {}; the SDK enables offline storage only when disabled, availSpaceInMb and "
                       "fileCount are all present".format(", ".join(missing)))
        mb = off.get("availSpaceInMb")
        if isinstance(mb, (int, float)) and 0 < mb < 1:
            out.append("offlineStorage availSpaceInMb is {} MB, a demonstration size; set it for the real device".format(mb))
        if "keepalive" in off:
            out.append("keepalive is inside offlineStorage, where the SDK never reads it; the MQTT keepalive comes from a "
                       "top-level SdkOptions['keepalive'] (default 60)")
    elif off is not None and "offlineStorage" in opts:
        out.append("offlineStorage is not a dict; offline storage stays off")
    if opts.get("skipValidation") is True:
        out.append("skipValidation is True; the SDK will not check values against the template")
    if opts.get("CameraOptions"):
        out.append("CameraOptions present: video is configured (see references/video-and-file-upload.md)")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Turn a sample-style firmware config into an env file.")
    ap.add_argument("firmware")
    ap.add_argument("-o", "--output", help="write the env file here instead of printing")
    ap.add_argument("--show-secrets", action="store_true", help="print the primary key instead of masking it")
    ap.add_argument("--report", action="store_true", help="print only the findings")
    a = ap.parse_args(argv)

    found, calls = read_assignments(a.firmware)
    rows = build(found)
    if not rows and "SdkOptions" not in found:
        die("no UniqueId or SdkOptions found at module level in {}; is this firmware for the iotconnect SDK?".format(
            a.firmware))
    issues = problems(found, rows, calls)

    if not a.report:
        lines = ["# Generated from {}".format(os.path.basename(a.firmware)),
                 "# Save as iotc.env in the project folder (git-ignored); the firmware and preflight.py load it"]
        for k, v, secret in rows:
            shown = v if (not secret or a.output or a.show_secrets) else "********"
            lines.append("{}={}".format(k, quote(shown)))
        lines.append("IOTC_DEBUG='0'")
        text = "\n".join(lines) + "\n"
        if a.output:
            fd = os.open(a.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(text)
            if os.name == "nt":
                print("wrote {} (Windows ignores the owner-only mode; restrict access to it yourself)".format(a.output))
            else:
                print("wrote {} (mode 600)".format(a.output))
        else:
            print(text, end="")
    if issues:
        print("\nFindings:" if not a.report else "Findings:")
        for i in issues:
            print("  - " + i)
    elif a.report:
        print("No problems found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
