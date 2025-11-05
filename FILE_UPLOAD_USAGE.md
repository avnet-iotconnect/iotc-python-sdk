# IoTConnect File Upload Feature

This document describes how to use the file upload feature in the IoTConnect Python SDK.

## Overview

The SDK now supports uploading files (images, documents, etc.) to AWS S3 buckets. Files can be uploaded to either:
- **IoTConnect S3 bucket** (ca=false): Uses IoT credentials directly
- **Customer Account S3 bucket** (ca=true): Uses STS to assume cross-account role

## Prerequisites

1. **Certificate-based authentication**: File upload requires device certificates
2. **File system configuration**: The sync response must include `p.fs` configuration with:
   - `buckets`: Array of S3 bucket configurations
   - `url`: IoT Core credential provider endpoint

## API Methods

### 1. UploadImage(file_path=None, file_stream=None, file_name=None)

Upload a file to S3 without publishing to MQTT.

**Parameters:**
- `file_path` (str, optional): Path to the file on disk
- `file_stream` (bytes/str, optional): File content as bytes or base64 string
- `file_name` (str, optional): Required if using file_stream

**Returns:** Dictionary with:
- `success` (bool): Upload success status
- `s3_key` (str): Full S3 object key
- `bucket` (str): S3 bucket name
- `url` (str): Short URL path for MQTT messages
- `error` (str): Error message if failed

**Example - Upload from file path:**
```python
result = sdk.UploadImage(file_path="/path/to/image.jpg")

if result["success"]:
    print(f"Uploaded to: {result['url']}")
else:
    print(f"Upload failed: {result['error']}")
```

**Example - Upload from bytes:**
```python
with open("image.jpg", "rb") as f:
    file_data = f.read()

result = sdk.UploadImage(file_stream=file_data, file_name="image.jpg")
```

**Example - Upload from base64:**
```python
import base64

with open("image.jpg", "rb") as f:
    file_data = base64.b64encode(f.read()).decode('utf-8')

result = sdk.UploadImage(file_stream=file_data, file_name="image.jpg")
```

### 2. UploadImageWithClassification(file_path=None, file_stream=None, file_name=None, classification=None, custom_attributes=None)

Upload a file to S3 and publish classification data to MQTT topic.

**Parameters:**
- `file_path` (str, optional): Path to the file on disk
- `file_stream` (bytes/str, optional): File content as bytes or base64 string
- `file_name` (str, optional): Required if using file_stream
- `classification` (str): Classification result (e.g., "defect", "good", "cat", etc.)
- `custom_attributes` (dict, optional): Additional attributes to include in MQTT message

**Returns:** Dictionary with:
- `success` (bool): Upload success status
- `s3_key` (str): Full S3 object key
- `bucket` (str): S3 bucket name
- `url` (str): Short URL path for MQTT messages
- `mqtt_published` (bool): Whether MQTT message was published
- `error` (str): Error message if failed

**Example - Basic classification:**
```python
result = sdk.UploadImageWithClassification(
    file_path="/path/to/image.jpg",
    classification="defect"
)

if result["success"] and result["mqtt_published"]:
    print(f"Upload and classification successful: {result['url']}")
```

**Example - With custom attributes:**
```python
result = sdk.UploadImageWithClassification(
    file_path="/path/to/image.jpg",
    classification="defect",
    custom_attributes={
        "confidence": 0.95,
        "defect_type": "scratch",
        "location": "top-left"
    }
)
```

**Example - From camera stream:**
```python
import cv2
import base64

# Capture from camera
cap = cv2.VideoCapture(0)
ret, frame = cap.read()

# Encode as JPEG
_, buffer = cv2.imencode('.jpg', frame)
file_data = buffer.tobytes()

# Upload with classification
result = sdk.UploadImageWithClassification(
    file_stream=file_data,
    file_name="camera_capture.jpg",
    classification="person_detected"
)
```

## MQTT Message Format

When using `UploadImageWithClassification`, the SDK publishes to the topic specified in `p.topics.fu` from the sync response (e.g., `$aws/rules/msg_d2c_file/{UID}/2.1/11`).

### Normal Device Payload:
```json
{
  "d": [{
    "d": {
      "url": "2025/11/04/72624ca2-4145-4148-b9f5-899961f6fc91-image.jpg",
      "c": "defect",
      "confidence": 0.95,
      "defect_type": "scratch"
    }
  }]
}
```

### Gateway Device Payload:
```json
{
  "d": [{
    "d": {
      "url": "2025/11/04/72624ca2-4145-4148-b9f5-899961f6fc91-image.jpg",
      "id": "child-device-unique-id",
      "tg": "device-tag",
      "c": "defect",
      "confidence": 0.95
    }
  }]
}
```

## S3 Path Structure

Files are uploaded to S3 using the following path structure:
```
device-uploads/{UniqueId}/{YYYY}/{MM}/{DD}/{GUID}-{filename}
```

Example:
```
device-uploads/mssql-reInvent/2025/11/04/72624ca2-4145-4148-b9f5-899961f6fc91-image.jpg
```

The `url` field in the MQTT message uses a shortened format:
```
{YYYY}/{MM}/{DD}/{GUID}-{filename}
```

## Sync Response Configuration

The file upload feature requires the following configuration in the sync response:

```json
{
  "p": {
    "fs": {
      "buckets": [
        {
          "bn": "iotc-612324506361",
          "ca": false
        }
      ],
      "url": "https://c1x1ly2rjmzjow.credentials.iot.us-east-1.amazonaws.com/role-aliases/filesupportalias/credentials"
    },
    "topics": {
      "fu": "$aws/rules/msg_d2c_file/mssql-reInvent/2.1/11"
    }
  }
}
```

## Error Handling

```python
result = sdk.UploadImage(file_path="/path/to/image.jpg")

if not result["success"]:
    error = result["error"]

    if "not initialized" in error:
        print("File upload not configured in sync response")
    elif "File not found" in error:
        print("Invalid file path")
    elif "Failed to get IoT credentials" in error:
        print("IoT credential provider error")
    elif "S3 upload failed" in error:
        print("S3 upload error")
    else:
        print(f"Unknown error: {error}")
```

## Supported File Types

The SDK automatically detects content type based on file extension:

- **Images**: .jpg, .jpeg, .png, .gif, .bmp, .tiff, .svg
- **Documents**: .pdf
- **Archives**: .zip, .tar, .gz
- **Data**: .json, .xml, .txt, .csv, .log

Unknown extensions are uploaded as `application/octet-stream`.

## Authentication Flow

### For ca=false (IoTConnect bucket):
1. Get temporary credentials from IoT Core credential provider
2. Upload directly to S3 using IoT credentials

### For ca=true (Customer bucket):
1. Get temporary credentials from IoT Core credential provider
2. Assume cross-account role via STS
3. Upload to S3 using cross-account credentials

## Complete Example

```python
from iotconnect.IoTConnectSDK import IoTConnectSDK
import time

# SDK configuration
sdkOptions = {
    "certificate": {
        "SSLKeyPath": "path/to/private.key",
        "SSLCertPath": "path/to/certificate.crt",
        "SSLCaPath": "path/to/root-ca.pem"
    },
    "cpid": "your-cpid",
    "env": "your-env",
    "IsDebug": True
}

# Initialize SDK
sdk = IoTConnectSDK("your-unique-id", sdkOptions)

# Wait for connection
time.sleep(5)

# Upload image with classification
result = sdk.UploadImageWithClassification(
    file_path="/path/to/defect_image.jpg",
    classification="defect_detected",
    custom_attributes={
        "confidence": 0.95,
        "defect_type": "scratch",
        "severity": "high"
    }
)

if result["success"]:
    print(f"Upload successful!")
    print(f"S3 Key: {result['s3_key']}")
    print(f"URL: {result['url']}")
    print(f"MQTT Published: {result['mqtt_published']}")
else:
    print(f"Upload failed: {result['error']}")

# Dispose SDK when done
sdk.Dispose()
```

## Troubleshooting

### File upload client not initialized
- Ensure sync response includes `p.fs` configuration
- Verify certificate-based authentication is configured
- Check SDK debug logs for initialization errors

### IoT credential errors
- Verify IoT Core credential provider URL is correct
- Check device certificates are valid and not expired
- Ensure device has permissions to access the credential provider

### S3 upload failures
- Check network connectivity
- Verify S3 bucket exists and is accessible
- Check bucket permissions and policies
- Review cross-account role configuration if ca=true

### MQTT publish failures
- Ensure device is connected to MQTT broker
- Verify file upload topic is configured in sync response
- Check MQTT connection status before uploading
