# Video streaming and file upload

Both features use temporary AWS credentials that the SDK obtains with the device's X.509
certificate, so both need certificate authentication.

## Video streaming (AWS Kinesis Video Streams)

The SDK starts and stops streaming itself. Firmware normally only supplies `CameraOptions`.

### Two modes

| Mode | What runs | Starts when |
|---|---|---|
| **PutMedia** | a GStreamer pipeline using the `kvssink` plugin | `ct` 112 without `webrtc`, or auto-start with an empty channel ARN |
| **WebRTC** | a separate process (`kvsWebRTCClientMaster.py`) acting as master on a signaling channel | `ct` 112 with `"webrtc": true` and `"carn"`, or auto-start with a channel ARN |

### How it is triggered

1. **Cloud command `ct` 112:**
   - `{"ct":112,"webrtc":true,"carn":"<channel ARN>"}` starts WebRTC. `carn` is required; without it nothing starts.
   - `{"ct":112}` or `"webrtc": false` starts PutMedia.
2. **Auto-start from the device's video settings (`vs`) received at sync:**
   - `as: true` and a non-empty `carn`: start WebRTC.
   - `as: true` and an empty `carn`: start PutMedia.
   - `as: false`: wait for a `ct` 112 command.
3. **`ct` 113** stops streaming. A second 112 while streaming is ignored.

Do not handle 112 or 113 in your callbacks. The SDK never delivers them there, although the README shows an example that does.

### Requirements

- **PutMedia:** Linux, GStreamer 1.0 with the base, good, bad and ugly plugins, the AWS KVS Producer SDK
  built with the GStreamer plugin so that `gst-inspect-1.0 kvssink` works, and a camera (USB or RTSP).
- **WebRTC:** extra Python packages that the SDK's `setup.py` does **not** install: `boto3`, `botocore`,
  `websockets`, `aiortc`, `aiohttp` (the repo's `sample-webrtc/requirements-webrtc.txt`). Install them with
  `pip install -r requirements-webrtc.txt`.
- Stopping a stream is supported on Linux only.
- The device role alias must allow Kinesis Video Streams actions. This is configured in AWS, not in firmware.

### Camera settings

```python
"CameraOptions": {
    "deviceport": "/dev/video0",
    "video": {"width": "640", "height": "480", "framerate": "30/1"}
}
```

If `deviceport` is missing the SDK tries to detect a video device. For WebRTC, only the numerator of
`framerate` is used (`"30/1"` becomes 30).

### Credential refresh and recovery (WebRTC)

The WebRTC process receives credentials valid for about an hour. A watchdog restarts the process
about five minutes before they expire, or immediately if it exits unexpectedly. Both times can be changed with the
environment variables `KVS_CREDENTIAL_TTL_SECONDS` (default 3600) and
`KVS_CREDENTIAL_REFRESH_MARGIN_SECONDS` (default 300). Expect a short gap in the stream at each restart.

### Connection loss

When the cloud connection drops, the SDK stops the active stream. That code path does not restart it,
so verify the behaviour on your device and send `ct` 112 again if needed.

### Manual start (advanced)

`start_kvs_webrtc_from_devicecert(channel_arn, uid, ca_path, cert_path, key_path, credential_endpoint,
camera_options, region)` can be called from firmware (the WebRTC sample does this), but prefer the
SDK-managed path. Never hardcode the channel ARN or credential endpoint, because they contain AWS account details.

## File upload (S3)

Needs the device to receive a file-storage configuration (`fs`) at sync. If it did not,
the calls return `success: False` with an explanatory `error`. They do not raise.

```python
result = Sdk.UploadImage(file_path="/data/frame.jpg")
# or from memory:
result = Sdk.UploadImage(file_stream=jpeg_bytes, file_name="frame.jpg")   # bytes or base64 text
if result["success"]:
    print(result["url"])          # short URL path; also has s3_key and bucket
else:
    print(result["error"])
```

```python
result = Sdk.UploadImageWithClassification(
    file_path="/data/frame.jpg",
    classification="defect",
    custom_attributes={"confidence": 0.95},
)
# result also has "mqtt_published"
```

- Files go either to the platform's bucket or to the customer's bucket through a cross-account role,
  depending on the platform configuration.
- Always check `result["success"]`. Only calls after `Dispose()` raise.
- `GetCredentials()` returns the raw temporary AWS credentials. Use it only for diagnostics and never print or log the values
  (the sample's test routine prints partial values; do not copy that).
