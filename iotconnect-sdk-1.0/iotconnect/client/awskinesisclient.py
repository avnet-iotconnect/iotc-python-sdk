from urllib.parse import urlparse
import requests
import subprocess
import signal
import os
import sys
import threading
import re

streampro = None

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
        )
        res_load = response.json()

        if(response.status_code == 200):
            return res_load["credentials"]["accessKeyId"], res_load["credentials"]["secretAccessKey"], res_load["credentials"]["sessionToken"]
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
    global streampro

    if 'linux' not in sys.platform:
        print("❌ GStreamer only supported on Linux.")
        return

    print("Starting GStreamer...")

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

    print(f"GStreamer command:\n{gst_command}")

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


def start_kvs_webrtc_from_devicecert(channel_arn, uid, cacert_path, devicecert_path, devicekey_path, aws_credential_endpoint, CameraOptions, region="us-east-1"):
    """
    Start a KVS WebRTC MASTER client using temporary credentials obtained via device certificate.

    - Obtains temporary credentials by calling the device credential endpoint (get_kinesis_cer).
    - Injects credentials into the child process environment.
    - Starts either the compiled binary (if present) or the local Python sample script (kvsWebRTCClientMaster.py).
    - Uses CameraOptions for device selection (function currently injects device selection into environment if needed).
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

    if not creds or len(creds) < 3:
        print("Failed to obtain temporary credentials from IoT credential endpoint.")
        return

    access_key, secret_key, session_token = creds

    # stop any existing stream
    try:
        if streampro:
            print("Stopping existing stream before starting KVS WebRTC...")
            os.killpg(os.getpgid(streampro.pid), signal.SIGTERM)
    except Exception:
        pass

    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = access_key
    env["AWS_SECRET_ACCESS_KEY"] = secret_key
    if session_token:
        env["AWS_SESSION_TOKEN"] = session_token
    env["AWS_DEFAULT_REGION"] = region

    # Build command for binary or python script. The sample script expects --channel-arn.
    if os.path.isfile(KVS_MASTER_CLIENT_EXE) and os.access(KVS_MASTER_CLIENT_EXE, os.X_OK):
        cmd = [KVS_MASTER_CLIENT_EXE, "--channel-arn", channel_arn]
        print(f"Using KVS binary: {KVS_MASTER_CLIENT_EXE}")
    elif os.path.isfile(KVS_MASTER_SCRIPT):
        # Credentials are already injected as AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY /
        # AWS_SESSION_TOKEN env vars above, so boto3 inside the script picks them up
        # automatically. Do NOT pass --use-device-certs which would cause the script to
        # re-fetch credentials from a .env file, ignoring the ones we injected.
        cmd = [sys.executable, KVS_MASTER_SCRIPT, "--channel-arn", channel_arn]
        print(f"Using KVS Python sample script: {KVS_MASTER_SCRIPT}")
    else:
        print("❌ No KVS master client found. Set KVS_MASTER_CLIENT_EXE or place kvsWebRTCClientMaster.py in this folder.")
        return

    # Optionally pass a file-path or device info, if supported by your client.
    deviceport = CameraOptions.get("deviceport") or detect_video_device()
    if deviceport:
        # The sample script provides --file-path for file playback; for device camera we don't pass.
        # If you want to pass file-path, uncomment the next line and adapt accordingly:
        # cmd += ["--file-path", deviceport]
        pass

    print("Starting KVS WebRTC MASTER client (env creds injected):")
    print(" ".join(cmd))

    try:
        streampro = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env,
            preexec_fn=os.setsid, text=False
        )

        threading.Thread(target=_pipe_reader, args=("KVMOUT", streampro.stdout), daemon=True).start()
        threading.Thread(target=_pipe_reader, args=("KVMERR", streampro.stderr), daemon=True).start()

        import time as _t
        _t.sleep(2.0)
        rc = streampro.poll()
        if rc is not None:
            print(f"❌ KVS WebRTC master client exited immediately with code {rc}")
    except FileNotFoundError:
        print("❌ KVS WebRTC master client binary/script not found.")
    except Exception as err:
        print(f"Error while starting KVS WebRTC master client: {err}")

    return streampro


def stop_gstreamer():
    global streampro

    if 'linux' not in sys.platform:
        print("Stopping GStreamer is supported only on Linux.")
        return

    if streampro:
        print("🛑 Stopping GStreamer...")
        os.killpg(os.getpgid(streampro.pid), signal.SIGTERM)


def _pipe_reader(prefix, pipe):
    try:
        for line in iter(pipe.readline, b''):
            print(f"{prefix}: {line.decode(errors='replace').rstrip()}")
    finally:
        pipe.close()