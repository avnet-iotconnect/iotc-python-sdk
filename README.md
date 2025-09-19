- Author: Softweb Solutions An Avnet Company
- Brief: /IOTCONNECT™ SDK: Software Development Kit 1.0
- Modified: 24-Sep-2024

This repository provides the **/IOTCONNECT™ Python SDK** with integrated support for **AWS Kinesis Video Streams (KVS)** for real-time video streaming from edge devices to the cloud. The SDK enables seamless video streaming through GStreamer-based pipeline with automatic credential management and stream lifecycle control.

## Key Features

- **Device-to-Cloud (D2C) Communication**: Send telemetry data, commands, and acknowledgments
- **Cloud-to-Device (C2D) Communication**: Receive commands, firmware updates, and configuration changes
- **AWS Kinesis Video Streams Integration**: Stream live video from edge cameras to AWS KVS
- **Automatic Stream Management**: Start/stop video streaming via cloud commands
- **X.509 Certificate Authentication**: Secure device authentication and credential management

This /IOTCONNECT™ Python SDK works with /IOTCONNECT™ Message version 2.1. You can find more details on the message version [here](https://docs.iotconnect.io/iotconnect/sdk/message-protocol/device-message-2-1/). Below is a step-by-step guide to help you install the SDK and run the sample.

## Getting Started

### Prerequisites

Before you install and run the firmware file, please ensure the following setup requirements:

#### System Requirements
1. **Python:** /IOTCONNECT™'s Python SDK supports versions 2.7, 3.5, 3.7 to 3.12, and 3.13. We recommend installing the most stable Python version 3.13.0.
2. **pip:** Compatible with your Python version.
3. **setuptools:** Required to manage Python packages.
4. **Operating System:**
   - **Linux**: Ubuntu 22.XX LTS (x86_64 or ARM) recommended for Kinesis Video Streams

#### For Kinesis Video Streams (Linux Only)
1. **Hardware Requirements:**
   - USB Camera (e.g., Logitech USB webcam) or RTSP-compatible IP camera
   - Minimum 512MB available RAM for video processing
   - ARM64 or x86_64 processor architecture

2. **Software Dependencies:**
   - GStreamer 1.0 and plugins
   - AWS Kinesis Video Streams Producer SDK C++
   - Development tools (cmake, build-essential, pkg-config)
   - SSL/TLS libraries (libssl-dev, libcurl4-openssl-dev)

#### /IOTCONNECT™ Platform Setup
1. **Device Registration:** Device must be registered and activated in /IOTCONNECT™ platform
2. **X.509 Certificates:** Device certificates, private key, and root CA certificate
3. **Platform Configuration:**
   - Company ID (CPID)
   - Environment (ENV)
   - Platform (PF) - typically "aws"
   - Discovery URL for your environment
4. **Device Template:** Must include video streaming capability if using KVS features
5. **Video Stream Configuration:** Configure video stream settings in /IOTCONNECT™ platform

### Installation

> **Note:** If you use multiple Python versions, use the appropriate `python` and `pip` commands for the installation process.

1. Create a `sample` folder on your machine and download the following files from Git:
    - `sample/iotconnect-sdk-1.0.tar.gz`
    - `sample/iotconnect-sdk-1.0-firmware-python_msg-2_1.py`

2. Use the terminal/command prompt to navigate to the sample folder:
    ```sh
    cd sample/
    ```

3. If your device already has a previous /IOTCONNECT™ Python SDK version, uninstall it before installing the latest version:
    ```sh
    pip list
    # Find your package name (iotconnect-sdk)
    pip uninstall iotconnect-sdk
    ```

4. **Kinesis Video Streams Producer SDK Setup (Ubuntu 22.XX):**

   **Step 4a: Install System Dependencies**
    ```sh
    sudo apt update
    sudo apt install -y git cmake build-essential pkg-config \
        libssl-dev libcurl4-openssl-dev liblog4cplus-dev \
        libgstreamer1.0-dev gstreamer1.0-tools \
        gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
        gstreamer1.0-libav
    ```

   **Step 4b: Build AWS KVS Producer SDK**
    ```sh
    # Create source directory
    mkdir -p ~/src && cd ~/src

    # Clone and build the SDK
    git clone https://github.com/awslabs/amazon-kinesis-video-streams-producer-sdk-cpp.git kvs-producer-sdk-cpp
    cd kvs-producer-sdk-cpp && mkdir build && cd build

    # Configure build with GStreamer plugin
    cmake .. -DBUILD_GSTREAMER_PLUGIN=ON -DBUILD_JNI=OFF -DBUILD_DEPENDENCIES=OFF

    # Build the SDK (this may take 10-15 minutes)
    make -j"$(nproc)"
    ```

   **Step 4c: Install GStreamer Plugin**
    ```sh
    # Make kvssink plugin discoverable by GStreamer
    sudo cp libgstkvssink.so /usr/lib/x86_64-linux-gnu/gstreamer-1.0/
    sudo ldconfig

    # For ARM64 systems, use:
    # sudo cp libgstkvssink.so /usr/lib/aarch64-linux-gnu/gstreamer-1.0/
    ```

   **Step 4d: Verify Installation**
    ```sh
    # Verify GStreamer can find the kvssink plugin
    gst-inspect-1.0 kvssink | head

    # Check camera device availability
    ls -la /dev/video*

    # Test camera capture (optional)
    gst-launch-1.0 v4l2src device=/dev/video0 ! videoconvert ! autovideosink
    ```

   **Troubleshooting:**
   - If `gst-inspect-1.0 kvssink` fails, ensure the plugin path is correct for your architecture
   - For permission issues with camera, add your user to the `video` group: `sudo usermod -a -G video $USER`
   - Restart your system after group changes

5. Install the required libraries:
    ```sh
    pip install iotconnect-sdk-1.0.tar.gz
    ```

6. **Configure your firmware file (`iotconnect-sdk-1.0-firmware-python_msg-2_1.py`):**

   **Basic Device Configuration:**
   ```python
   UniqueId = "your-device-unique-id"  # Device ID from /IOTCONNECT™ platform
   ```

   **SDK Options Configuration:**
   ```python
   SdkOptions = {
       "certificate": {
           "SSLKeyPath": "/path/to/device-private.pem.key",  # Device private key
           "SSLCertPath": "/path/to/device-certificate.pem.crt",  # Device certificate
           "SSLCaPath": "/path/to/root-CA.pem"  # Root CA certificate
       },
       "offlineStorage": {
           "disabled": False,
           "availSpaceInMb": 0.01,
           "fileCount": 5,
           "keepalive": 60
       },
       "skipValidation": False,
       "discoveryUrl": "Use your environment URL",
       "IsDebug": True,
       "cpid": "your-company-id",
       "sId": "your-solution-id",  # Optional: use sId OR env+cpid
       "env": "your-environment",
       "pf": "aws",

       # Kinesis Video Streams Configuration (Linux only)
       "CameraOptions": {
           "deviceport": "/dev/video0",  # USB camera device path
           "video": {
               "width": "640",      # Video width in pixels
               "height": "480",     # Video height in pixels
               "framerate": "30/1"  # Frame rate (30 fps)
           }
       }
   }
   ```

   **Required Configuration Steps:**
   - Replace certificate paths with actual file locations
   - Update device credentials (UniqueId, cpid, env)
   - Verify camera device path (`/dev/video0`, `/dev/video1`, etc.)
   - Adjust video resolution based on camera capabilities
   - Update sensor attributes to match your /IOTCONNECT™ device template

## Explanation

Import the SDK package to initialize the SDK object:
```python
from iotconnect import IoTConnectSDK
```

### Prerequisite Configuration

```python
UniqueId = "<<Device UniqueID>>"
```
- `UniqueId`: Your device uniqueId

#### SdkOptions

`SdkOptions` is for SDK configuration. It needs to be passed in the SDK object initialization call. Manage the configuration as per your device authentication type.

```python
SdkOptions = {
    "certificate": { 
        "SSLKeyPath": "",
        "SSLCertPath": "",
        "SSLCaPath": ""
    },
    "offlineStorage": {
        "disabled": False,
        "availSpaceInMb": 0.01,
        "fileCount": 5,
        "keepalive": 60
    },
    "skipValidation": False,
    "devicePrimaryKey": "Your Key",
    "discoveryUrl": "Your Discovery Url",
    "IsDebug": False,
    "cpid": "Your CPID",
    "sId": "Your SID",
    "env": "Your env",
    "pf": "Your pf"
}
```
- `sdkOptions` is mandatory for "certificate" X.509 device authentication type.
- `certificate`: Requires the path of the certificate file. Mandatory for X.509/SSL device CA-signed or self-signed authentication type.
    - `SSLKeyPath`: Your device key
    - `SSLCertPath`: Your device certificate
    - `SSLCaPath`: Root CA certificate
    - Windows + Linux OS: Use "/" forward slash (Example: Windows: "E:/folder1/folder2/certificate", Linux: "/home/folder1/folder2/certificate")
- `offlineStorage`: Configuration for offline data storage.
    - `disabled`: False = offline data storing, True = not storing offline data.
    - `availSpaceInMb`: File size of offline data in MB.
    - `fileCount`: Number of files to create for offline data.
- `devicePrimaryKey`: Mandatory for Symmetric Key Authentication. Obtain it from the /IOTCONNECT™ UI portal: Device -> Select device -> Info(Tab) -> Connection Info -> Device Connection.

> **Note:**  
> SSL/X.509 device CA-signed or self-signed authentication type requires `sdkOptions`. Define the proper certification path.  
> If you do not provide offline storage, the firmware file will set the default settings as defined above.  
> Extensive data storage may harm your device. Once memory is full, SDK execution may stop.

### Initialize the SDK object and connect to the cloud

```python
with IoTConnectSDK(UniqueId, SdkOptions, DeviceConectionCallback) as Sdk:
    # Your code here
```

### Receive command from cloud-to-device

```python
def DeviceCallback(msg):
    print(json.dumps(msg))
    if cmdType == 0:
        data = msg
        if data is not None:
            if "ack" in data and data["ack"]:
                if "id" in data:
                    Sdk.sendAckCmd(data["ack"], 2, "successful", data["id"])  # Executed (Cloud Only) = 0, Failed = 1, Executed Ack = 2
                else:
                    Sdk.sendAckCmd(data["ack"], 2, "successful")  # Executed (Cloud Only) = 0, Failed = 1, Executed Ack = 2
```

### Receive OTA command from cloud-to-device

```python
def DeviceFirmwareCallback(msg):
    print(json.dumps(msg))
    if cmdType == 1:
        if ("urls" in data) and data["urls"]:
            for url_list in data["urls"]:
                if "tg" in url_list:
                    for i in device_list:
                        if "tg" in i and (i["tg"] == url_list["tg"]):
                            Sdk.sendOTAAckCmd(data["ack"], 0, "successful", i["id"])  # Success=0, Failed=1, Executed/DownloadingInProgress=2, Executed/DownloadDone=3, Failed/DownloadFailed=4
                else:
                    Sdk.sendOTAAckCmd(data["ack"], 0, "successful")  # Success=0, Failed=1, Executed/DownloadingInProgress=2, Executed/DownloadDone=3, Failed/DownloadFailed=4
```

### Device Connect/Disconnect Command

```python
def DeviceConectionCallback(msg):  
    if cmdType == 116:
        # Device connection status e.g. data["command"] = true(connected) or false(disconnected)
        print(json.dumps(msg))
```

### Receive twin from cloud-to-device

```python
def TwinUpdateCallback(msg):
    print(json.dumps(msg))
    sdk.UpdateTwin(key, value)
```
- `key`: Desired property key received from Twin callback message
- `value`: Value of the respective desired property

### Publish data to cloud (device-to-cloud)

```python
def sendBackToSDK(sdk, dataArray):
    sdk.SendData(dataArray)
    time.sleep(interval)
```

### Get device attributes in firmware

```python
def attributeDetails(data):
    print("Attribute received in firmware")
    print(data)
```

### Request list of attributes for device type

```python
devices = sdk.GetAttributes()
```

### Standard data input format for gateway and non-gateway device

#### 1. For non-gateway device

```python
data = [{"temperature": random.randint(30, 50)}]
dObj = [{
    "uniqueId": UniqueId,
    "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    "data": data
}]
```

#### 2. For gateway and multiple child devices

```python
dObj = [
    {
        "uniqueId": "<< Gateway Device UniqueId >>",
        "time": "<< date >>",
        "data": {"temperature": random.randint(30, 50)}
    },
    {
        "uniqueId": "<< Child DeviceId >>", 
        "time": "<< date >>",
        "data": {"temperature": random.randint(30, 50)}
    }
]
sendBackToSDK(Sdk, dObj)
```
- `time`: Date format should be `"2021-01-24T10:06:17.857Z"`
- `data`: JSON format, e.g., `{"temperature": 15.55, "gyroscope": { 'x': -1.2 }}`

### Kinesis Video Streams Integration

The SDK provides seamless integration with AWS Kinesis Video Streams for real-time video streaming from edge devices.

#### Video Stream Configuration

```python
# Camera configuration in SdkOptions
"CameraOptions": {
    "deviceport": "/dev/video0",  # Camera device path
    "video": {
        "width": "640",           # Resolution width
        "height": "480",          # Resolution height
        "framerate": "30/1"       # Frame rate (30 fps)
    }
}
```

#### Supported Camera Configurations

| Resolution | Use Case | Bandwidth (approx) |
|------------|----------|-------------------|
| 320x240 | Low bandwidth/testing | ~200 Kbps |
| 640x480 | Standard monitoring | ~500 Kbps |
| 1280x720 (HD) | High quality monitoring | ~1.5 Mbps |
| 1920x1080 (FHD) | Maximum quality | ~3-5 Mbps |

#### Stream Control Commands

Video streaming is controlled via /IOTCONNECT™ cloud commands:

**Start Streaming (Command Type 112):**
- Automatically triggered when `"as": true` (auto-start) is configured
- Can be manually triggered via /IOTCONNECT™ platform
- Establishes AWS credentials and starts GStreamer pipeline

**Stop Streaming (Command Type 113):**
- Stops the active video stream
- Terminates GStreamer process and releases resources

#### Stream Lifecycle Management

The SDK handles the complete video streaming lifecycle:

1. **Credential Management**: Automatically obtains temporary AWS credentials using device certificates
2. **Stream Creation**: Creates Kinesis Video Stream if not exists
3. **Pipeline Setup**: Configures GStreamer pipeline with optimal settings
4. **Quality Control**: Applies encoding settings for efficient streaming
5. **Error Handling**: Monitors stream health and handles reconnections
6. **Resource Cleanup**: Properly releases resources when streaming stops

#### Stream Monitoring

```python
def DeviceCallback(msg):
    cmdType = msg["ct"] if "ct" in msg else None

    if cmdType == 112:  # Stream start command
        print("Video streaming started")
        # Add your custom logic here

    elif cmdType == 113:  # Stream stop command
        print("Video streaming stopped")
        # Add your custom logic here
```

#### Network Requirements

- **Minimum Upload Bandwidth**: 1 Mbps for 640x480 @ 30fps
- **Recommended Upload Bandwidth**: 2-3x the video bitrate for stability
- **Latency**: < 500ms RTT to AWS region for optimal performance
- **Ports**: Ensure outbound HTTPS (443) and streaming ports are open

#### Troubleshooting Video Streams

**Common Issues and Solutions:**

1. **Camera Not Found**
   ```bash
   # Check available cameras
   ls -la /dev/video*

   # Test camera access
   gst-launch-1.0 v4l2src device=/dev/video0 ! videoconvert ! autovideosink
   ```

2. **GStreamer Pipeline Errors**
   ```bash
   # Verify kvssink plugin
   gst-inspect-1.0 kvssink

   # Check GStreamer installation
   gst-launch-1.0 --version
   ```

3. **AWS Credentials Issues**
   - Verify certificate paths in SdkOptions
   - Ensure device certificates have proper permissions
   - Check AWS region configuration

4. **Stream Quality Issues**
   - Reduce resolution or frame rate
   - Check network bandwidth availability
   - Monitor CPU usage during streaming

**Performance Optimization:**

- Use hardware encoding if available: `h264enc` → `v4l2h264enc`
- Adjust bitrate based on network conditions
- Consider reducing frame rate in low bandwidth scenarios
- Monitor system resources during streaming

### Disconnect the device from the cloud

```python
sdk.Dispose()
```