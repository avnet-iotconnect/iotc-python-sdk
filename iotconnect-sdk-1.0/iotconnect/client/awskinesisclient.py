import requests
import subprocess
import signal
import os

streampro = None

def get_kinesis_cer(cpid, uid, cacert, devicecert, devicekey, aws_endpoint):

    iot_cred_url = "https://" + aws_endpoint + "/role-aliases/kinesisvideoalias/credentials"
    print(iot_cred_url)
 
    try:
        
        response = requests.get(
           
            url = iot_cred_url,
            cert = ( devicecert, devicekey ),
            verify = cacert,
            headers = {
                "x-amzn-iot-thingname": cpid + "-" + uid
            },
        )
        res_load = response.json()

        if(response.status_code == 200):
            return res_load["credentials"]["accessKeyId"], res_load["credentials"]["secretAccessKey"], res_load["credentials"]["sessionToken"]
        else:
            print("Failed in getting Kinesis Device access and Secret key")
        
    except requests.RequestException as e:
        print(f"Error obtaining credentials from IoT: {e}")
        return



def start_gstreamer(stream_name, access_key, secret_key, session_token):

    global streampro

    gst_command = (
        f"gst-launch-1.0 v4l2src do-timestamp=TRUE device=/dev/video0 ! "
        "videoconvert ! video/x-raw,format=I420,width=640,height=480,framerate=30/1 ! "
        "x264enc bframes=0 key-int-max=45 bitrate=500 ! "
        "video/x-h264,stream-format=avc,alignment=au,profile=baseline ! "
        f"kvssink stream-name={stream_name} storage-size=512 "
        f"access-key={access_key} "
        f"secret-key={secret_key} "
        f"session-token={session_token} "  # Include the session token
        "aws-region=us-east-1 "
    )
    
    print("Starting GStreamer...")
    print(gst_command)
    streampro = subprocess.Popen(gst_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=os.setsid)
    print(streampro)
    output, errors = streampro.communicate()
    # print(output)
    return streampro


def stop_gstreamer():
    global streampro
    print("Stopping GStreamer...")
    os.killpg(os.getpgid(streampro.pid), signal.SIGTERM)  # Kill entire process group
