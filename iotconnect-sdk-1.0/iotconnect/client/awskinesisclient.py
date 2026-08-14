from urllib.parse import urlparse
import requests
import subprocess
import signal
import os
import sys
import threading
import re
import time
from datetime import datetime, timezone

streampro = None

# Bumped every time we deliberately start or stop the KVS WebRTC subprocess, so the
# watchdog thread (see _kvs_watchdog) can tell an unexpected exit (crash/OOM) apart
# from one we caused ourselves, and knows not to resurrect a stream we meant to stop.
_kvs_session_id = 0

# AWS IoT role-alias credentials are typically valid for 1 hour. Credentials here are
# injected into the subprocess as env vars at launch and can't be refreshed in place,
# so the watchdog proactively restarts the process this long before they expire.
CREDENTIAL_TTL_SECONDS = int(os.getenv('KVS_CREDENTIAL_TTL_SECONDS', '3600'))
CREDENTIAL_REFRESH_MARGIN_SECONDS = int(os.getenv('KVS_CREDENTIAL_REFRESH_MARGIN_SECONDS', '300'))

# Prefer the local Python sample in this client folder by default.
KVS_MASTER_SCRIPT = os.path.join(os.path.dirname(__file__), "kvsWebRTCClientMaster.py")
KVS_MASTER_CLIENT_EXE = "/usr/local/bin/kvsWebrtcClientMasterGst"  # optional compiled binary (if you have it)

def get_kinesis_cer(uid, cacert, devicecert, devicekey, aws_credential_endpoint):

    if not aws_credential_endpoint:
        raise ValueError("AWS credential endpoint is required")

    url = aws_credential_endpoint.strip()
    try:
        p = urlparse(url)
        if p.scheme != "https" or not url.endswith("/credentials"):
            raise ValueError(f"Bad role-alias URL: {url}. URL must use HTTPS and end with '/credentials'")
        if not p.netloc:
            raise ValueError(f"Invalid URL format: {url}. Missing domain name")
    except Exception as e:
        raise ValueError(f"Failed to parse URL '{url}': {e}")

    print("Kinesis creds endpoint (final):", repr(url))
    print("Using Thing name:", uid)

    try:

        response = requests.get(

            url = url,
            cert = ( devicecert, devicekey ),
            verify = cacert,
            headers = {
                "x-amzn-iot-thingname": uid
            },
            # Bounds how long a stalled/unreachable IoT endpoint can block the caller.
            timeout = (10, 20),
        )
        res_load = response.json()

        if(response.status_code == 200):
            creds = res_load["credentials"]
            # Includes "expiration" so callers (see _kvs_watchdog) know when to refresh.
            return creds["accessKeyId"], creds["secretAccessKey"], creds["sessionToken"], creds.get("expiration")
        else:
            print("Response from IoT: (non 200)", res_load)
            print("Failed in getting Kinesis Device access and Secret key")
            return
        
    except requests.RequestException as e:
        print(f"Error obtaining credentials from IoT: {e}")
        return

def _extract_region_from_arn(arn):
    """Extract AWS region from a channel ARN.
    ARN format: arn:aws:kinesisvideo:<region>:<account-id>:channel/<name>/<id>
    """
    try:
        parts = (arn or "").split(":")
        if len(parts) >= 4 and parts[3]:
            return parts[3]
    except Exception:
        pass
    return None


def _parse_role_alias_endpoint(url):
    """Split a role-alias credentials URL into (host, role_alias).
    URL format: https://<host>/role-aliases/<role-alias>/credentials
    """
    try:
        parsed = urlparse(url or "")
        parts = parsed.path.strip("/").split("/")
        if parsed.netloc and len(parts) == 3 and parts[0] == "role-aliases" and parts[2] == "credentials":
            return parsed.netloc, parts[1]
    except Exception:
        pass
    return None, None


def detect_video_device():
    """Detects the first /dev/video* device."""
    try:
        devices = [d for d in os.listdir("/dev") if d.startswith("video")]
        if devices:
            video_device = f"/dev/{devices[0]}"
            print(f"🎥 Using video device: {video_device}")
            return video_device
        else:
            print("⚠️ No video devices found.")
            return None
    except Exception as e:
        print(f"Error detecting video device: {e}")
        return None


def detect_mic_device():
    """Detects the first available audio capture device (usually webcam mic)."""
    try:
        result = subprocess.run(["arecord", "-l"], capture_output=True, text=True)
        lines = result.stdout.splitlines()

        for line in lines:
            match = re.search(r"card (\d+): .*device (\d+):", line)
            if match:
                card, device = match.groups()
                mic = f"hw:{card},{device}"
                print(f"🎤 Using mic device: {mic}")
                return mic

        print("⚠️ No audio capture devices found.")
        return None
    except Exception as e:
        print(f"Error detecting mic device: {e}")
        return None


def start_gstreamer(stream_name, access_key, secret_key, session_token, CameraOptions, region="us-east-1"):
    global streampro, _kvs_session_id

    if 'linux' not in sys.platform:
        print("❌ GStreamer only supported on Linux.")
        return

    print("Starting GStreamer...")

    # Stops any pre-existing stream (WebRTC or GStreamer) first, so it doesn't stay
    # orphaned holding the camera device. Bumps _kvs_session_id so a stopped WebRTC
    # watchdog doesn't resurrect it.
    _kvs_session_id += 1
    try:
        if streampro:
            print("Stopping existing stream before starting GStreamer...")
            os.killpg(os.getpgid(streampro.pid), signal.SIGTERM)
    except Exception:
        pass
    try:
        subprocess.run(["pkill", "-f", "gst-launch-1.0"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    deviceport = CameraOptions.get("deviceport") or detect_video_device()
    videoWidth = CameraOptions["video"]["width"]
    videoHeight = CameraOptions["video"]["height"]
    videoFrate = CameraOptions["video"]["framerate"]
    mic_device = detect_mic_device()

    # --- Build GStreamer command ---
    if mic_device:
        # Video + Audio pipeline
        gst_command = (
            "gst-launch-1.0 -v "
            f"kvssink stream-name={stream_name} storage-size=512 "
            f"access-key={access_key} secret-key={secret_key} "
            f"session-token={session_token} aws-region={region} name=sink "
            f"v4l2src device={deviceport} do-timestamp=true ! "
            f"videoconvert ! video/x-raw,format=I420,width={videoWidth},height={videoHeight},framerate={videoFrate} ! "
            "x264enc bframes=0 key-int-max=45 bitrate=800 speed-preset=ultrafast tune=zerolatency ! "
            "video/x-h264,stream-format=avc,alignment=au,profile=baseline ! "
            "h264parse ! video/x-h264,stream-format=avc,alignment=au ! sink. "
            f"alsasrc device={mic_device} ! audioconvert ! audioresample ! "
            "audio/x-raw,rate=48000,channels=1,format=S16LE,layout=interleaved ! "
            "voaacenc bitrate=128000 ! aacparse ! audio/mpeg,mpegversion=4 ! sink."
        )
    else:
        # Video-only pipeline (no muxer needed)
        gst_command = (
            "gst-launch-1.0 -v "
            f"v4l2src device={deviceport} do-timestamp=true ! "
            f"videoconvert ! video/x-raw,format=I420,width={videoWidth},height={videoHeight},framerate={videoFrate} ! "
            "x264enc bframes=0 key-int-max=45 bitrate=800 speed-preset=ultrafast tune=zerolatency ! "
            "video/x-h264,stream-format=avc,alignment=au ! "
            f"kvssink stream-name={stream_name} storage-size=512 "
            f"access-key={access_key} secret-key={secret_key} "
            f"session-token={session_token} aws-region={region}"
        )

    print(f"GStreamer command: gst-launch-1.0 -v executed")

    try:
        streampro = subprocess.Popen(
            gst_command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            preexec_fn=os.setsid, text=False
        )

        threading.Thread(target=_pipe_reader, args=("GSTOUT", streampro.stdout), daemon=True).start()
        threading.Thread(target=_pipe_reader, args=("GSTERR", streampro.stderr), daemon=True).start()

        import time as _t
        _t.sleep(2.0)
        rc = streampro.poll()
        if rc is not None:
            print(f"❌ gst-launch-1.0 exited immediately with code {rc}")
    except FileNotFoundError:
        print("❌ GStreamer is NOT installed.")
    except Exception as err:
        print(f"Error while Starting GStreamer: {err}")

    return streampro


def _kvs_watchdog(proc, session_id, expiration, restart_args):
    """
    Restarts the subprocess on an unexpected exit (e.g. OOM-kill), or proactively
    before its injected AWS credentials expire (~1hr TTL, can't be refreshed in
    place). No-ops if _kvs_session_id has since moved on (a deliberate stop/restart
    happened elsewhere - see stop_gstreamer).
    """
    deadline = CREDENTIAL_TTL_SECONDS - CREDENTIAL_REFRESH_MARGIN_SECONDS
    if expiration:
        try:
            expires_at = datetime.fromisoformat(expiration.replace('Z', '+00:00'))
            deadline = (expires_at - datetime.now(timezone.utc)).total_seconds() - CREDENTIAL_REFRESH_MARGIN_SECONDS
        except Exception:
            pass

    rc = None
    try:
        rc = proc.wait(timeout=max(deadline, 0))
    except subprocess.TimeoutExpired:
        pass  # reached the credential-refresh window while the process was still healthy

    if session_id != _kvs_session_id:
        return

    if rc is None:
        print("KVS WebRTC: proactively restarting to refresh credentials before they expire")
    else:
        print(f"KVS WebRTC: process exited unexpectedly (code={rc}), restarting")
    start_kvs_webrtc_from_devicecert(*restart_args)


def start_kvs_webrtc_from_devicecert(channel_arn, uid, cacert_path, devicecert_path, devicekey_path, aws_credential_endpoint, CameraOptions, region="us-east-1"):
    """
    Start a KVS WebRTC MASTER client using temporary credentials obtained via device certificate.

    - Obtains temporary credentials by calling the device credential endpoint (get_kinesis_cer).
    - Injects credentials into the child process environment.
    - Starts either the compiled binary (if present) or the local Python sample script (kvsWebRTCClientMaster.py).
    - Uses CameraOptions for device selection (function currently injects device selection into environment if needed).
    - A background watchdog (_kvs_watchdog) restarts the process if it exits unexpectedly
      or before its injected credentials expire.
    """
    global streampro

    # Extract region from ARN when not explicitly provided
    arn_region = _extract_region_from_arn(channel_arn)
    if arn_region:
        region = arn_region

    # obtain temporary credentials using device certs
    creds = None
    try:
        creds = get_kinesis_cer(uid, cacert_path, devicecert_path, devicekey_path, aws_credential_endpoint)
    except Exception as ex:
        print(f"Failed to get kinesis credentials: {ex}")
        return

    if not creds or len(creds) < 4:
        print("Failed to obtain temporary credentials from IoT credential endpoint.")
        return

    access_key, secret_key, session_token, expiration = creds

    # stop any existing stream
    global _kvs_session_id
    _kvs_session_id += 1
    session_id = _kvs_session_id
    try:
        if streampro:
            print("Stopping existing stream before starting KVS WebRTC...")
            os.killpg(os.getpgid(streampro.pid), signal.SIGTERM)
    except Exception:
        pass
    # Belt-and-braces cleanup by name, in case a previous run's subprocess is still
    # alive holding the camera device even though the in-memory streampro handle
    # doesn't know about it.
    try:
        subprocess.run(["pkill", "-f", "kvsWebRTCClientMaster.py"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = access_key
    env["AWS_SECRET_ACCESS_KEY"] = secret_key
    if session_token:
        env["AWS_SESSION_TOKEN"] = session_token
    env["AWS_DEFAULT_REGION"] = region

    # Not read for credentials today - the AWS_ACCESS_KEY_ID/etc above (already fetched by
    # this function) are what the child actually uses, since --use-device-certs is
    # deliberately not passed below. Populated anyway so these env vars are correct and
    # available if --use-device-certs is ever enabled here in the future (kvsWebRTCClientMaster.py's
    # --iot-credential-provider/--thing-name/--role-alias/--cert-file/--key-file/--root-ca
    # CLI args each default to os.getenv() of the exact same names) - see IOTC_SDK_KVS_NOTES.md.
    credential_provider_host, role_alias = _parse_role_alias_endpoint(aws_credential_endpoint)
    if credential_provider_host:
        env["IOT_CREDENTIAL_PROVIDER"] = credential_provider_host
    if role_alias:
        env["ROLE_ALIAS"] = role_alias
    env["THING_NAME"] = uid
    env["CERT_FILE"] = devicecert_path
    env["KEY_FILE"] = devicekey_path
    env["ROOT_CA"] = cacert_path

    # Build command for binary or python script. The sample script expects --channel-arn.
    if os.path.isfile(KVS_MASTER_CLIENT_EXE) and os.access(KVS_MASTER_CLIENT_EXE, os.X_OK):
        cmd = [KVS_MASTER_CLIENT_EXE, "--channel-arn", channel_arn]
        print(f"Using KVS binary: {KVS_MASTER_CLIENT_EXE}")
    elif os.path.isfile(KVS_MASTER_SCRIPT):
        # Credentials are already injected as AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY /
        # AWS_SESSION_TOKEN env vars above, so boto3 inside the script picks them up
        # automatically. Do NOT pass --use-device-certs here - that would make the child
        # re-fetch its own credentials via the cert/role-alias env vars above instead of
        # using the ones already fetched and injected by this function.
        cmd = [sys.executable, KVS_MASTER_SCRIPT, "--channel-arn", channel_arn]
    else:
        print("❌ No KVS master client found. Set KVS_MASTER_CLIENT_EXE or place kvsWebRTCClientMaster.py in this folder.")
        return

    # Pass CameraOptions (device/resolution/framerate) through to the subprocess.
    # kvsWebRTCClientMaster.py's MediaTrackManager reads these straight from the
    # environment - without this, it silently fell back to its own 1280x720@30
    # defaults regardless of what SdkOptions["CameraOptions"] configured.
    deviceport = CameraOptions.get("deviceport") or detect_video_device()
    if deviceport:
        env["CAMERA_DEVICE"] = deviceport
    video = CameraOptions.get("video") or {}
    if video.get("width"):
        env["CAMERA_WIDTH"] = str(video["width"])
    if video.get("height"):
        env["CAMERA_HEIGHT"] = str(video["height"])
    if video.get("framerate"):
        # CameraOptions uses GStreamer-style fraction strings ("30/1");
        # kvsWebRTCClientMaster.py does int(os.getenv("CAMERA_FRAMERATE")) - a bare
        # "30/1" would raise ValueError, so take the numerator only.
        env["CAMERA_FRAMERATE"] = str(video["framerate"]).split("/")[0]

    print("Starting KVS WebRTC client")
    # print(" ".join(cmd))

    try:
        streampro = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env,
            preexec_fn=os.setsid, text=False
        )

        threading.Thread(target=_pipe_reader, args=("KVMOUT", streampro.stdout), daemon=True).start()
        threading.Thread(target=_pipe_reader, args=("KVMERR", streampro.stderr), daemon=True).start()

        time.sleep(2.0)
        rc = streampro.poll()
        if rc is not None:
            print(f"❌ KVS WebRTC master client exited immediately with code {rc}")
        else:
            restart_args = (channel_arn, uid, cacert_path, devicecert_path, devicekey_path,
                             aws_credential_endpoint, CameraOptions, region)
            threading.Thread(
                target=_kvs_watchdog,
                args=(streampro, session_id, expiration, restart_args),
                daemon=True,
            ).start()
    except FileNotFoundError:
        print("❌ KVS WebRTC master client binary/script not found.")
    except Exception as err:
        print(f"Error while starting KVS WebRTC client: {err}")

    return streampro


def stop_gstreamer():
    global streampro, _kvs_session_id

    if 'linux' not in sys.platform:
        print("Stopping GStreamer is supported only on Linux.")
        return

    if streampro:
        print("🛑 Stopping GStreamer...")
        # Invalidates the watchdog first, so it doesn't mistake this deliberate stop
        # for a crash and restart the process it was just asked to stop.
        _kvs_session_id += 1
        # Catches ProcessLookupError if the process already exited on its own, and
        # always clears streampro afterward so stale handles aren't reused.
        try:
            os.killpg(os.getpgid(streampro.pid), signal.SIGTERM)
        except ProcessLookupError:
            print("KVS: process already exited, nothing to stop.")
        except Exception as err:
            print(f"Error while stopping stream: {err}")
        streampro = None


def _pipe_reader(prefix, pipe):
    try:
        for line in iter(pipe.readline, b''):
            print(f"{prefix}: {line.decode(errors='replace').rstrip()}")
    finally:
        pipe.close()