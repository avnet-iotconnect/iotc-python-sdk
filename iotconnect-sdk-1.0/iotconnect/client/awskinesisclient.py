from urllib.parse import urlparse
import requests
import subprocess
import signal
import os
import sys
import threading

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



def start_gstreamer(stream_name, access_key, secret_key, session_token, CameraOptions,region="us-east-1"):

    global streampro

    if 'linux' in sys.platform :
        print("stream name : ", stream_name)
        print("CameraOptions : ",CameraOptions)

        deviceport = CameraOptions["deviceport"]
        videoWidth = CameraOptions["video"]["width"]
        videoHeight = CameraOptions["video"]["height"]
        videoFrate = CameraOptions["video"]["framerate"]

        gst_command = (
            f"gst-launch-1.0 v4l2src do-timestamp=TRUE device={deviceport} ! "
            f"videoconvert ! video/x-raw,format=I420,width={videoWidth},height={videoHeight},framerate={videoFrate} ! "
            "clockoverlay time-format=\"%a %B %d, %Y %I:%M:%S %p\" ! "
            "x264enc bframes=0 key-int-max=45 bitrate=500 ! "
            "video/x-h264,stream-format=avc,alignment=au,profile=baseline ! "
            f"kvssink stream-name={stream_name} storage-size=512 "
            f"access-key={access_key} "
            f"secret-key={secret_key} "
            f"session-token={session_token} "  # Include the session token
            f"aws-region={region}"
        )
        
    print("CameraOptions : ", CameraOptions)
    print("Starting GStreamer...")
    print(gst_command)

    try:
        streampro = subprocess.Popen(
            gst_command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            preexec_fn=os.setsid, text=False
        )
        # Mirror child output so errors are visible
        threading.Thread(target=_pipe_reader, args=("GSTOUT", streampro.stdout), daemon=True).start()
        threading.Thread(target=_pipe_reader, args=("GSTERR", streampro.stderr), daemon=True).start()

        # Health check
        import time as _t
        _t.sleep(1.0)
        rc = streampro.poll()
        if rc is not None:
            print(f"gst-launch-1.0 exited immediately with code {rc}")
    except FileNotFoundError:
        print("GStreamer is NOT installed.")
    except Exception as err:
        print("Error while Starting GStreamer :", err)
    return streampro


def stop_gstreamer():
    global streampro

    if 'linux' in sys.platform :
        print("Stopping GStreamer...")
        os.killpg(os.getpgid(streampro.pid), signal.SIGTERM)  # Kill entire process group
    else:
        print("Stopping GStreamer Only avalaible in LINUX")

def _pipe_reader(prefix, pipe):
    try:
        for line in iter(pipe.readline, b''):
            print(f"{prefix}: {line.decode(errors='replace').rstrip()}")
    finally:
        try:
            pipe.close()
        except Exception:
            pass