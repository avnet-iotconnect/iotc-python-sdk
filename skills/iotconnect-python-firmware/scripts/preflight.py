#!/usr/bin/env python3
"""
Read-only pre-flight check for firmware that uses the /IOTCONNECT Python SDK.

It changes nothing and prints no secrets. Settings come from arguments or from the same
environment variables the firmware template uses (IOTC_*), and from <project>/iotc.env, which is
loaded automatically (real environment variables win). Unset certificate and template paths
are looked up in the project layout: certs/<UniqueId>/ or certs/, and templates/ or template/.
It also checks that the private key and iotc.env are git-ignored.

Examples (run from the project folder, or pass --project):
  python3 preflight.py
  python3 preflight.py --check-network
  python3 preflight.py --video --webrtc

Exit status: 0 when every check passes (warnings allowed), 1 when any check fails.
"""

import argparse
import importlib.util
import os
import shutil
import stat
import sys
import urllib.parse
import urllib.request

results = []


def record(level, name, detail=""):
    results.append((level, name, detail))
    print("[{:<4}] {}{}".format(level, name, " - " + detail if detail else ""))


def ok(name, detail=""):
    record("PASS", name, detail)


def warn(name, detail=""):
    record("WARN", name, detail)


def fail(name, detail=""):
    record("FAIL", name, detail)


def has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def check_python():
    v = sys.version_info
    if v < (3, 6):
        fail("python version", "3.6 or newer is required (found {}.{})".format(v[0], v[1]))
    else:
        ok("python version", "{}.{}.{}".format(v[0], v[1], v[2]))


def check_packages():
    if has_module("iotconnect"):
        ok("iotconnect package importable")
    else:
        fail("iotconnect package importable", "install the SDK: pip install iotconnect-sdk-1.0.tar.gz")
    for mod in ("paho.mqtt.client", "ntplib", "requests"):
        if has_module(mod.split(".")[0]):
            ok("dependency " + mod.split(".")[0])
        else:
            fail("dependency " + mod.split(".")[0], "missing; reinstall the SDK")


def check_identity(a):
    if a.unique_id:
        ok("unique id set")
    else:
        fail("unique id set", "set IOTC_UNIQUE_ID or --unique-id")
    if a.sid or (a.cpid and a.env):
        ok("cpid + env, or sId, set")
    else:
        fail("cpid + env, or sId, set", "the SDK needs cpid and env, or sId")
    if a.pf:
        ok("platform (pf) set", a.pf)
    else:
        warn("platform (pf) set", "empty; usually 'aws'")
    if a.discovery_url:
        if "http" in a.discovery_url:
            ok("discovery URL looks valid", a.discovery_url)
        else:
            fail("discovery URL looks valid", "must contain http")


def check_file(label, path, key=False):
    if not path:
        fail(label, "path not set")
        return
    if not os.path.isfile(path):
        fail(label, "file not found: " + path)
        return
    if not os.access(path, os.R_OK):
        fail(label, "not readable: " + path)
        return
    try:
        with open(path, "r", errors="ignore") as fh:
            head = fh.read(4096)
    except OSError as ex:
        fail(label, "cannot read: {}".format(ex))
        return
    if "BEGIN" not in head:
        warn(label, "no PEM header found in " + path)
    else:
        ok(label, path)
    if key and os.name == "posix":
        mode = os.stat(path).st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            warn(label + " permissions", "readable by other users; run chmod 600 on it")


def check_auth(a):
    if a.primary_key:
        ok("authentication", "symmetric key supplied (value not shown)")
        return
    check_file("device private key", a.key, key=True)
    check_file("device certificate", a.cert)
    check_file("root CA", a.ca)
    if a.ca and not a.ca.lower().endswith(".pem"):
        warn("root CA file name", "the SDK raises ERR[05] when the root CA file name does not end in .pem (except authType 3); rename or copy it")


def check_template(a):
    """Compare the device template with the settings given on the command line."""
    import json
    try:
        with open(a.template, encoding="utf-8-sig") as fh:
            t = json.load(fh)
    except (OSError, ValueError) as ex:
        fail("device template", "cannot read {}: {}".format(a.template, ex))
        return
    if not isinstance(t, dict) or not isinstance(t.get("attributes"), list):
        fail("device template", "no 'attributes' list; this is not a device template")
        return
    ok("device template", "{} ({} attributes, {} settings, {} commands)".format(
        t.get("name"), len(t["attributes"]), len(t.get("settings") or []), len(t.get("commands") or [])))
    if str(t.get("messageVersion")) != "2.1":
        warn("template message version", "{} (this SDK speaks 2.1)".format(t.get("messageVersion")))
    at = _int(t.get("authType"))
    has_cert = bool(a.key and a.cert)
    if at is None:
        warn("template auth type", "{!r} is not a number; export the device's real template".format(t.get("authType")))
    elif at in (2, 3, 7) and a.primary_key and not has_cert:
        fail("template auth type", "authType {} needs certificates, but only a primary key was given".format(at))
    elif at == 5 and not a.primary_key:
        fail("template auth type", "authType 5 needs a device primary key")
    else:
        ok("template auth type", "authType {}".format(at))
    freq = _int((t.get("properties") or {}).get("dataFrequency"))
    if freq:
        interval = _int(a.send_interval)
        if interval is not None and interval < freq:
            fail("send interval", "IOTC_SEND_INTERVAL is {} s but the template dataFrequency is {} s; "
                 "SendData returns None and sends nothing for calls inside the window".format(interval, freq))
        else:
            ok("template data frequency", "{} s; send no faster than this".format(freq))
    if any(a_.get("tag") for a_ in t["attributes"] if isinstance(a_, dict)):
        ok("gateway template", "attributes are tagged; children use the attributes of their tag "
           "(references/gateway-and-children.md)")


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def check_tls_env():
    if os.environ.get("PYTHONHTTPSVERIFY"):
        ok("HTTPS verification", "PYTHONHTTPSVERIFY is set, so the SDK keeps Python's default verification")
    else:
        warn("HTTPS verification",
             "PYTHONHTTPSVERIFY is not set; the SDK turns off HTTPS certificate verification for this process")


def check_network(a):
    if not (a.discovery_url and a.pf and (a.sid or (a.cpid and a.env))):
        warn("discovery request", "skipped; identity settings incomplete")
        return
    if a.sid:
        path = "/api/v2.1/dsdk/sid/{}?pf={}".format(urllib.parse.quote(a.sid), urllib.parse.quote(a.pf))
    else:
        path = "/api/v2.1/dsdk/cpid/{}/env/{}?pf={}".format(
            urllib.parse.quote(a.cpid), urllib.parse.quote(a.env), urllib.parse.quote(a.pf))
    url = a.discovery_url.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            ok("discovery request", "HTTP {}".format(resp.status))
    except Exception as ex:  # report every kind of network failure the same way
        fail("discovery request", "{}: {}".format(type(ex).__name__, ex))


def check_video(a):
    if sys.platform.startswith("linux"):
        ok("video platform", "linux")
    else:
        fail("video platform", "video streaming is Linux only")
    dev = a.camera or ""
    if dev and os.path.exists(dev):
        ok("camera device", dev)
    elif dev:
        fail("camera device", "not found: " + dev)
    else:
        warn("camera device", "not specified; the SDK will try to detect one")
    if shutil.which("gst-inspect-1.0"):
        ok("gst-inspect-1.0 available (run 'gst-inspect-1.0 kvssink' to confirm the plugin)")
    else:
        fail("GStreamer tools", "gst-inspect-1.0 not found; install GStreamer 1.0 and the KVS producer plugin")


def check_webrtc():
    for mod in ("boto3", "botocore", "websockets", "aiortc", "aiohttp"):
        if has_module(mod):
            ok("webrtc dependency " + mod)
        else:
            fail("webrtc dependency " + mod, "pip install -r requirements-webrtc.txt")


# ----------------------------------------------------------------------------- project layout
# Convention (references/sample-config-map.md, "Project layout"):
#   certs/<UniqueId>/  or  certs/      private key, device certificate, root CA (.pem)
#   templates/  or  template/          the device template exported from the platform
#   iotc.env                           settings; certs/ and iotc.env are git-ignored

def _files(folder):
    try:
        return sorted(os.path.join(folder, f) for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)))
    except OSError:
        return []


def _pick(files, tests):
    for test in tests:
        hits = [f for f in files if test(os.path.basename(f).lower())]
        if len(hits) == 1:
            return hits[0]
    return ""


def discover_layout(a, root):
    """Fill unset certificate and template paths from the project layout. Prints what it picked."""
    cert_dirs = [os.path.join(root, "certs", a.unique_id)] if a.unique_id else []
    cert_dirs.append(os.path.join(root, "certs"))
    if not a.primary_key and not (a.key and a.cert and a.ca):
        for d in cert_dirs:
            files = _files(d)
            if not files:
                continue
            key = a.key or _pick(files, [lambda n: n.startswith("pk_"), lambda n: n.endswith(".key"),
                                        lambda n: "private" in n])
            cert = a.cert or _pick(files, [lambda n: n.startswith("cert_"), lambda n: n.endswith(".crt"),
                                          lambda n: n.endswith("certificate.pem.crt")])
            ca = a.ca or _pick([f for f in files if f not in (key, cert)],
                               [lambda n: "rootca" in n or "root-ca" in n or "root_ca" in n,
                                lambda n: n.startswith("amazonroot"), lambda n: n.endswith((".pem", ".crt"))])
            if key or cert or ca:
                found = [(n, v) for n, v, old in (("IOTC_KEY", key, a.key), ("IOTC_CERT", cert, a.cert),
                                                  ("IOTC_CA", ca, a.ca)) if v and not old]
                a.key, a.cert, a.ca = key, cert, ca
                warn("project layout: certificates",
                     "found in {}/ but not set in the environment; the firmware reads only IOTC_* variables. "
                     "Add to iotc.env: {}".format(os.path.relpath(d, root).replace(os.sep, "/"), "  ".join(
                         "{}='{}'".format(n, os.path.relpath(v, root).replace(os.sep, "/")) for n, v in found)))
                break
    if not a.template:
        for d in ("templates", "template"):
            hits = [f for f in _files(os.path.join(root, d)) if f.lower().endswith(".json")]
            if len(hits) == 1:
                a.template = hits[0]
                ok("project layout: template", "{} (set IOTC_TEMPLATE to choose another)".format(
                    os.path.relpath(hits[0], root).replace(os.sep, "/")))
                break
            if len(hits) > 1:
                warn("project layout: template", "{} templates in {}/; set IOTC_TEMPLATE to the one attached to "
                     "this device".format(len(hits), d))
                break


def _git_ignored(path, root):
    """True / False, or None when git cannot tell (no git, not a repo, ownership refusal)."""
    git = shutil.which("git")
    if not git:
        return None
    import subprocess
    try:
        inside = subprocess.run([git, "-C", root, "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, text=True, timeout=10)
        if inside.returncode != 0:
            return None
        r = subprocess.run([git, "-C", root, "check-ignore", "-q", path], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return {0: True, 1: False}.get(r.returncode)


def check_secrets_layout(a, root):
    """Secrets must not be committable, and the downloaded certificate zip should not linger."""
    secrets = [("device private key", a.key), ("env file", os.path.join(root, "iotc.env"))]
    for label, path in secrets:
        if not path or not os.path.isfile(path):
            continue
        ignored = _git_ignored(os.path.abspath(path), root)
        if ignored is False:
            fail(label + " git-ignored", "{} could be committed; add it (or its folder) to .gitignore".format(
                os.path.relpath(path, root)))
        elif ignored is True:
            ok(label + " git-ignored")
    for d in {os.path.dirname(os.path.abspath(p)) for p in (a.key, a.cert) if p}:
        zips = [f for f in _files(d) if f.lower().endswith(".zip")]
        if zips:
            warn("certificate download", "{} still in {}; it holds a copy of the private key. Delete it once "
                 "extracted".format(", ".join(os.path.basename(z) for z in zips), os.path.relpath(d, root)))


def load_env_file(path):
    """Load KEY=VALUE lines without overriding the environment. Returns the number of keys read."""
    base = os.path.dirname(os.path.abspath(path))
    n = 0
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            k, v = (x.strip() for x in line.split("=", 1))
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1].replace("'\\''", "'")
            if k in ("IOTC_KEY", "IOTC_CERT", "IOTC_CA", "IOTC_TEMPLATE") and v and not os.path.isabs(v):
                v = os.path.normpath(os.path.join(base, v))
            os.environ.setdefault(k, v)
            n += 1
    return n


def main(argv=None):
    del results[:]
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--project", default=os.getcwd())
    pre.add_argument("--env-file")
    known, _ = pre.parse_known_args(argv)
    env_file = known.env_file or os.environ.get("IOTC_ENV_FILE") or os.path.join(known.project, "iotc.env")
    loaded = load_env_file(env_file) if os.path.isfile(env_file) else None
    env = os.environ.get
    p = argparse.ArgumentParser(description="Read-only pre-flight check for /IOTCONNECT firmware.")
    p.add_argument("--unique-id", default=env("IOTC_UNIQUE_ID", ""))
    p.add_argument("--cpid", default=env("IOTC_CPID", ""))
    p.add_argument("--sid", default=env("IOTC_SID", ""))
    p.add_argument("--env", default=env("IOTC_ENV", ""))
    p.add_argument("--pf", default=env("IOTC_PF", "aws"))
    p.add_argument("--discovery-url", default=env("IOTC_DISCOVERY_URL", "https://discovery.iotconnect.io"))
    p.add_argument("--key", default=env("IOTC_KEY", ""))
    p.add_argument("--cert", default=env("IOTC_CERT", ""))
    p.add_argument("--ca", default=env("IOTC_CA", ""))
    p.add_argument("--primary-key", default=env("IOTC_PRIMARY_KEY", ""))
    p.add_argument("--camera", default=env("IOTC_CAMERA", ""))
    p.add_argument("--send-interval", default=env("IOTC_SEND_INTERVAL", ""),
                   help="seconds between sends; compared with the template dataFrequency")
    p.add_argument("--check-network", action="store_true",
                   help="also request the public discovery URL the SDK uses at start-up")
    p.add_argument("--template", default=env("IOTC_TEMPLATE", ""), help="device template JSON to check against the settings")
    p.add_argument("--video", action="store_true", help="check Kinesis video prerequisites")
    p.add_argument("--webrtc", action="store_true", help="check WebRTC Python dependencies")
    p.add_argument("--project", default=os.getcwd(),
                   help="project folder holding certs/, templates/ and iotc.env (default: current folder)")
    p.add_argument("--env-file", help="settings file to load (default: <project>/iotc.env)")
    a = p.parse_args(argv)

    if loaded is not None:
        ok("settings file", "{} ({} entries loaded; environment variables take precedence)".format(env_file, loaded))
    else:
        warn("settings file", "no iotc.env in {}; using environment variables only".format(known.project))
    check_python()
    check_packages()
    check_identity(a)
    discover_layout(a, a.project)
    check_auth(a)
    check_secrets_layout(a, a.project)
    check_tls_env()
    if a.template:
        check_template(a)
    if a.check_network:
        check_network(a)
    if a.video:
        check_video(a)
    if a.webrtc:
        check_webrtc()

    failed = sum(1 for r in results if r[0] == "FAIL")
    warned = sum(1 for r in results if r[0] == "WARN")
    print("\n{} failed, {} warning(s), {} passed".format(
        failed, warned, sum(1 for r in results if r[0] == "PASS")))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
