from urllib.parse import urlparse
import requests
import subprocess
import signal
import os
import sys
import threading
import re

streampro = None

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

    try:
        for line in iter(pipe.readline, b''):
            print(f"{prefix}: {line.decode(errors='replace').rstrip()}")
    finally:
        try:
            pipe.close()
        except Exception:
            pass

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
    gst_command = (
        "gst-launch-1.0 -v "
        f"v4l2src device={deviceport} do-timestamp=true ! "
        f"videoconvert ! video/x-raw,format=I420,width={videoWidth},height={videoHeight},framerate={videoFrate} ! "
        "x264enc bframes=0 key-int-max=45 bitrate=800 speed-preset=ultrafast tune=zerolatency ! "
        "video/x-h264,stream-format=avc,alignment=au ! queue ! mux. "
    )

    if mic_device:
        gst_command += (
            f"alsasrc device={mic_device} ! audio/x-raw,rate=44100,channels=1,format=S16LE ! "
            "avenc_aac bitrate=64000 ! queue ! mux. "
        )

    gst_command += (
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