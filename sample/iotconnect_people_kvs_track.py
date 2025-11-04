"""
  ******************************************************************************
  * @file : iotconnect-sdk-1.0-firmware-python_msg-2_1.py
  * @author : Softweb Solutions + Integrated People Tracking
  * @modify : 2025-10-31
  * @brief : IoTConnect + KVS Live Tracking | Sends EXACT telemetry format
  ******************************************************************************
"""
import sys
import json
import time
import threading
import random
from iotconnect import IoTConnectSDK
from datetime import datetime, timezone
import os
import cv2
import numpy as np
import boto3
from botocore.exceptions import ClientError
from ultralytics import YOLO
import queue
import subprocess

# === GLOBAL CONFIGURATION ===
UniqueId = "reInvent"
Sdk = None
interval = 10
readyStatus = False
directmethodlist = {}
ACKdirect = []
device_list = []

# === TRACKING STATE (Thread-safe) ===
latest_tracks = []                    # Current frame detections
id_map = {}                           # internal_id → display_id
next_display_id = 1                   # Next sequential ID
display_id_lock = threading.Lock()

frame_counter = 0                     # Telemetry frame ID
frame_counter_lock = threading.Lock()

total_unique_people = 0               # Cumulative unique people ever seen
total_unique_lock = threading.Lock()

# === YOLO MODEL (Global) ===
model = None
device = 'cpu'

# === PEOPLE TRACKER CLASS ===
class IntegratedPeopleTracker:
    def __init__(self, aws_credentials, camera_index=0, fps=10, width=640, height=480,
                 model_path="./config/yolov10n.pt", tracker_config="./config/bytetrack_custom.yaml"):
        self.camera_index = camera_index
        self.fps = fps
        self.width = width
        self.height = height
        self.model_path = model_path
        self.tracker_config = tracker_config
        self.cap = None
        self.running = threading.Event()
        self.frame_queue = queue.Queue(maxsize=2)
        self.detection_lock = threading.Lock()

        # Store AWS credentials
        self.aws_credentials = aws_credentials

        # KVS Streaming
        self.stream_name = "mssql-reInvent"
        self.aws_region = 'us-east-1'

        # Create boto3 client with credentials from IoTConnect SDK
        self.kvs = boto3.client(
            'kinesisvideo',
            region_name=self.aws_region,
            aws_access_key_id=aws_credentials['accessKeyId'],
            aws_secret_access_key=aws_credentials['secretAccessKey'],
            aws_session_token=aws_credentials.get('sessionToken')  # Optional for temporary credentials
        )

        self.gst_process = None
        self.stdin_lock = threading.Lock()

        print(f"[KVS] Initialized with credentials:")
        print(f"  Access Key ID: {aws_credentials['accessKeyId'][:10]}...")
        print(f"  Region: {self.aws_region}")

        global model, device
        if model is None:
            print("[TRACKER] Loading YOLOv10n + Stable Tracker...")
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Model not found: {model_path}")
            if not os.path.exists(tracker_config):
                raise FileNotFoundError(f"Tracker config not found: {tracker_config}")
            model = YOLO(model_path)
            device = 'cuda' if model.device.type == 'cuda' else 'cpu'
            model.to(device)
            model.tracker = tracker_config
            print(f"[TRACKER] Model loaded on {device} | Tracker: {tracker_config}")

    def setup_kvs_stream(self):
        try:
            self.kvs.describe_stream(StreamName=self.stream_name)
            print(f"[KVS] Stream exists: {self.stream_name}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"[KVS] Creating stream: {self.stream_name}")
                self.kvs.create_stream(
                    StreamName=self.stream_name,
                    DataRetentionInHours=24,
                    MediaType='video/h264'
                )
                time.sleep(5)
            else:
                raise

    def start_kvs_streaming(self):
        # Set AWS credentials as environment variables for GStreamer kvssink
        env = os.environ.copy()
        env['AWS_ACCESS_KEY_ID'] = self.aws_credentials['accessKeyId']
        env['AWS_SECRET_ACCESS_KEY'] = self.aws_credentials['secretAccessKey']
        if 'sessionToken' in self.aws_credentials:
            env['AWS_SESSION_TOKEN'] = self.aws_credentials['sessionToken']
        env['AWS_DEFAULT_REGION'] = self.aws_region

        pipeline = (
            f"gst-launch-1.0 -e fdsrc ! "
            f"videoparse width={self.width} height={self.height} framerate={self.fps}/1 format=bgr ! "
            f"videoconvert ! video/x-raw,format=I420 ! "
            f"x264enc bitrate=512 tune=zerolatency speed-preset=superfast key-int-max=45 bframes=0 ! "
            f"h264parse ! video/x-h264,stream-format=avc,alignment=au ! "
            f"kvssink stream-name={self.stream_name} aws-region={self.aws_region}"
        )
        try:
            self.gst_process = subprocess.Popen(
                pipeline, shell=True, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, bufsize=0,
                env=env  # Pass credentials to GStreamer
            )
            time.sleep(2)
            if self.gst_process.poll() is not None:
                err = self.gst_process.stderr.read().decode()
                raise RuntimeError(f"GStreamer failed: {err}")
            print(f"[KVS] Streaming started → {self.stream_name}")
            return True
        except Exception as e:
            print(f"[KVS] Failed: {e}")
            return False

    def track_people(self, frame):
        try:
            results = model.track(
                frame, conf=0.5, iou=0.7, classes=[0], persist=True, verbose=False
            )[0]
            tracks = []
            if results.boxes.id is not None:
                for box, tid, conf in zip(results.boxes.xyxy, results.boxes.id, results.boxes.conf):
                    x1, y1, x2, y2 = map(int, box.cpu().numpy())
                    tracks.append({
                        'box': [x1, y1, x2, y2],
                        'internal_id': int(tid.item()),
                        'conf': float(conf.item())
                    })
            return tracks
        except Exception as e:
            print(f"[TRACKER] Error: {e}")
            return []

    def remap_ids(self, raw_tracks):
        global next_display_id, total_unique_people
        with display_id_lock:
            remapped = []
            for t in raw_tracks:
                internal_id = t['internal_id']
                if internal_id not in id_map:
                    id_map[internal_id] = next_display_id
                    next_display_id += 1
                    # Update total unique count
                    with total_unique_lock:
                        total_unique_people = next_display_id - 1
                remapped.append({
                    'box': t['box'],
                    'id': id_map[internal_id],
                    'conf': t['conf']
                })
            return remapped

    def detection_worker(self):
        while self.running.is_set():
            try:
                frame = self.frame_queue.get(timeout=1)
                raw_tracks = self.track_people(frame)
                display_tracks = self.remap_ids(raw_tracks)
                with self.detection_lock:
                    global latest_tracks
                    latest_tracks = display_tracks
                self.frame_queue.task_done()
            except queue.Empty:
                continue

    def draw_detections(self, frame):
        h, w = frame.shape[:2]
        with self.detection_lock:
            tracks = latest_tracks.copy()

        for t in tracks:
            x1, y1, x2, y2 = t['box']
            display_id = t['id']
            conf = t['conf']
            np.random.seed(display_id % 100)
            color = tuple(int(x) for x in np.random.random(3) * 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"Person {display_id} ({conf:.0%})"
            cv2.putText(frame, label, (x1, max(y1 - 10, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            cv2.circle(frame, (cx, cy), 4, color, -1)

        with total_unique_lock:
            total = total_unique_people
        current = len(tracks)
        overlay = f"People: {current} / {total}"
        cv2.putText(frame, overlay, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        cv2.putText(frame, datetime.now().strftime("%H:%M:%S"), (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        return frame

    def safe_write_frame(self, frame):
        try:
            with self.stdin_lock:
                if self.gst_process and self.gst_process.stdin:
                    self.gst_process.stdin.write(frame.tobytes())
                    self.gst_process.stdin.flush()
        except Exception as e:
            print(f"[KVS] Write error: {e}")
            self.running.clear()

    def start(self):
        print("="*60)
        print("LIVE PEOPLE TRACKING → KVS + IoTConnect")
        print("="*60)
        self.setup_kvs_stream()
        if not self.start_kvs_streaming():
            return False
        self.running.set()
        threading.Thread(target=self.detection_worker, daemon=True).start()
        self.cap = cv2.VideoCapture(self.camera_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        if not self.cap.isOpened():
            print("[ERROR] Camera failed")
            return False
        print("Tracking + Streaming started")
        return True

    def run_frame_loop(self):
        frame_time = 1.0 / self.fps
        try:
            while self.running.is_set():
                start = time.time()
                ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue
                annotated = self.draw_detections(frame)
                self.safe_write_frame(annotated)
                try:
                    if self.frame_queue.full():
                        self.frame_queue.get_nowait()
                    self.frame_queue.put_nowait(frame.copy())
                except:
                    pass
                elapsed = time.time() - start
                if elapsed < frame_time:
                    time.sleep(frame_time - elapsed)
        except KeyboardInterrupt:
            print("\n[TRACKER] Stopping...")
        finally:
            self.cleanup()

    def cleanup(self):
        self.running.clear()
        if self.cap:
            self.cap.release()
        if self.gst_process:
            try:
                self.gst_process.stdin.close()
                self.gst_process.terminate()
                self.gst_process.wait(timeout=5)
            except:
                pass
        print("Tracker cleaned up")

# === IoTConnect SDK OPTIONS ===
SdkOptions = {
    "certificate": {
        "SSLKeyPath": "/home/softweb/mk/aws_mk/aws_kvs_iotconnect_vf/iotconnect_reinvent_cert/pk_reInvent demo.pem",
        "SSLCertPath": "/home/softweb/mk/aws_mk/aws_kvs_iotconnect_vf/iotconnect_reinvent_cert/cert_reInvent demo.crt",
        "SSLCaPath": "/home/softweb/mk/aws_mk/aws_kvs_iotconnect_vf/iotconnect_reinvent_cert/SFSRootCAG2.pem"
    },
    "offlineStorage": {
        "disabled": False,
        "availSpaceInMb": 0.01,
        "fileCount": 5,
        "keepalive": 60
    },
    "skipValidation": False,
    "discoveryUrl": "https://jzbybwq654.execute-api.us-east-1.amazonaws.com/Prod/",
    "IsDebug": True,
    "cpid": "mssql",
    "sId": "",
    "env": "preqa",
    "pf": "aws",
    "CameraOptions": {
        "deviceport": "/dev/video0",
        "video": {
            "width": "640",
            "height": "480",
            "framerate": "10/1"
        }
    }
}

# === CALLBACKS ===
def DeviceCallback(msg):
    global Sdk
    print("Command →", json.dumps(msg))
    if msg and "ct" in msg and msg["ct"] == 0 and "ack" in msg:
        ack_id = msg.get("id")
        if ack_id:
            Sdk.sendAckCmd(msg["ack"], 2, "successful", ack_id)
        else:
            Sdk.sendAckCmd(msg["ack"], 2, "successful")

def DeviceFirmwareCallback(msg):
    global Sdk, device_list
    print("OTA →", json.dumps(msg))
    if msg and "ct" in msg and msg["ct"] == 1 and "ack" in msg:
        for url in msg.get("urls", []):
            tg = url.get("tg")
            for dev in device_list:
                if dev.get("tg") == tg:
                    Sdk.sendOTAAckCmd(msg["ack"], 5, "successful", dev["id"])
                    break
            else:
                Sdk.sendOTAAckCmd(msg["ack"], 5, "successful")

def DeviceConectionCallback(msg):
    if msg and "ct" in msg and msg["ct"] == 116:
        print("Connection →", json.dumps(msg))

def TwinUpdateCallback(msg):
    global Sdk
    if msg and "desired" in msg and "reported" not in msg:
        for k in msg["desired"]:
            if k not in ["version", "uniqueId"]:
                Sdk.UpdateTwin(k, msg["desired"][k])

def DirectMethodCallback(msg, methodname, rId):
    global Sdk
    print(f"Direct Method: {methodname} | {msg}")
    Sdk.DirectMethodACK(msg, 200, rId)

def onReady(data):
    global readyStatus
    print("Attributes Synced →", data)
    readyStatus = True

# === EXACT TELEMETRY SENDER ===
# === EXACT TELEMETRY SENDER ===
# === EXACT TELEMETRY SENDER – ALWAYS ONE MESSAGE (fault) ===
def sendTrackingDataToIoTConnect(sdk):
    global frame_counter, total_unique_people

    with frame_counter_lock:
        current_frame_id = frame_counter
        frame_counter += 1

    clf_array = []
    with display_id_lock:
        for t in latest_tracks:
            clf_array.append({
                "tracker_id": int(t['id']),
                "class": "person",
                "confidence": float(round(t['conf'], 2))
            })

    # ✅ FIX: Always send valid array (even empty)
    if len(clf_array) == 0:
        clf_array = [{"tracker_id": 0, "class": "person", "confidence": 0.0}]

    with total_unique_lock:
        total_count = total_unique_people

    payload = {
        "dg": {
            "ppl": int(total_count),
            "fid": int(current_frame_id),
            "clf": clf_array
        }
    }

    dObj = [{
        "uniqueId": UniqueId,
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "data": payload
    }]

    if sdk.SendData(dObj):
        print(f"✅ REPORTING → {payload}")
    else:
        print("❌ FAILED")

# === MAIN ===
def main():
    global Sdk, readyStatus, device_list

    try:
        # Initialize IoTConnect SDK first
        with IoTConnectSDK(UniqueId, SdkOptions, DeviceConectionCallback) as sdk:
            Sdk = sdk
            Sdk.onDeviceCommand(DeviceCallback)
            Sdk.onTwinChangeCommand(TwinUpdateCallback)
            Sdk.onOTACommand(DeviceFirmwareCallback)
            Sdk.onReady(onReady)
            device_list = Sdk.Getdevice()
            Sdk.getTwins()

            print("IoTConnect SDK initialized, waiting for device ready...")

            # Wait for SDK to be ready
            while not readyStatus:
                print("Waiting for device ready...")
                time.sleep(2)

            print("Device ready! Getting AWS credentials from IoTConnect SDK...")

            # Get AWS credentials from IoTConnect SDK
            credentials = Sdk.GetAWSCredentials()
            if not credentials:
                print("Failed to get AWS credentials from SDK")
                return

            print(f"✓ AWS Credentials obtained successfully")
            print(f"  Access Key ID: {credentials['accessKeyId'][:10]}...")
            print(f"  Secret Key: {credentials['secretAccessKey'][:10]}...")
            if 'sessionToken' in credentials:
                print(f"  Session Token: {credentials['sessionToken'][:20]}...")

            # Initialize tracker with AWS credentials
            print("\nInitializing People Tracker with KVS streaming...")
            tracker = IntegratedPeopleTracker(
                aws_credentials=credentials,
                fps=10,
                width=640,
                height=480
            )

            if not tracker.start():
                print("Failed to start tracker")
                return

            tracking_thread = threading.Thread(target=tracker.run_frame_loop, daemon=True)
            tracking_thread.start()

            print("\n" + "="*60)
            print("IoTConnect + Tracking Active | Sending telemetry every 10s")
            print("="*60)

            while True:
                if readyStatus:
                    sendTrackingDataToIoTConnect(Sdk)
                else:
                    print("Device disconnected, waiting...")
                time.sleep(10)

    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'tracker' in locals():
            tracker.cleanup()
        if Sdk:
            Sdk.Dispose()
        print("Shutdown complete")

if __name__ == "__main__":
    main()