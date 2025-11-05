# File Upload Integration Test Guide

## Overview

The sample file `iotconnect-sdk-1.0-firmware-python_msg-2_1.py` has been updated with comprehensive file upload integration testing capabilities.

## What Was Added

### New Test Function: `testFileUpload(sdk)`

This function runs 4 different file upload tests:

1. **Test 1**: Upload image from file path (requires `test_image.jpg`)
2. **Test 2**: Upload image with classification from file path (requires `test_image.jpg`)
3. **Test 3**: Upload from byte stream (in-memory file)
4. **Test 4**: Upload byte stream with classification

### New Global Variables

```python
file_upload_counter = 0          # Tracks number of upload tests
test_file_upload = False         # Enable/disable file upload testing
```

## How to Run Integration Tests

### Option 1: Run Test Once at Startup

1. **Enable file upload testing** by setting the flag to `True`:
   ```python
   test_file_upload = True  # Set to True to enable file upload testing
   ```

2. **(Optional)** Create a test image in the same directory:
   ```bash
   # Copy any JPG image to the sample directory
   cp /path/to/your/image.jpg test_image.jpg
   ```

3. **Run the sample**:
   ```bash
   python sample/iotconnect-sdk-1.0-firmware-python_msg-2_1.py
   ```

4. The file upload test will run once after the SDK is ready, then continue with normal telemetry.

### Option 2: Run Periodic Tests

To run file upload tests every 5 telemetry loops (every 50 seconds):

1. Enable file upload testing (set `test_file_upload = True`)

2. Uncomment the periodic test code in the main loop:
   ```python
   # Change from:
   # if test_file_upload and loop_counter % 5 == 0:
   #     print("Firmware :: Running periodic file upload test...")
   #     testFileUpload(Sdk)

   # To:
   if test_file_upload and loop_counter % 5 == 0:
       print("Firmware :: Running periodic file upload test...")
       testFileUpload(Sdk)
   ```

3. Run the sample

### Option 3: Manual Testing

Call the test function manually from anywhere in your code:
```python
testFileUpload(Sdk)
```

## Test Details

### Test 1 & 2: File Path Upload
**Requirements:**
- Create `test_image.jpg` in the sample directory
- Can be any image file (JPG, PNG, etc.)

**What it tests:**
- `UploadImage(file_path)` method
- `UploadImageWithClassification(file_path, classification, custom_attributes)` method
- File reading from disk
- MQTT message publishing with custom attributes

**Output:**
```
Firmware :: Test 1: UploadImage from file path
Firmware :: Upload Success!
Firmware ::   S3 Key: device-uploads/device-id/2025/11/04/guid-test_image.jpg
Firmware ::   Bucket: iotc-612324506361
Firmware ::   URL: 2025/11/04/guid-test_image.jpg

Firmware :: Test 2: UploadImageWithClassification from file path
Firmware :: Upload Success!
Firmware ::   S3 Key: device-uploads/device-id/2025/11/04/guid-test_image.jpg
Firmware ::   URL: 2025/11/04/guid-test_image.jpg
Firmware ::   MQTT Published: True
```

### Test 3: Byte Stream Upload
**Requirements:** None (creates test content in memory)

**What it tests:**
- `UploadImage(file_stream, file_name)` method
- Uploading from bytes
- Dynamic filename generation

**Content:** Creates a text file with timestamp

**Output:**
```
Firmware :: Test 3: UploadImage from byte stream
Firmware :: Upload Success!
Firmware ::   S3 Key: device-uploads/device-id/2025/11/04/guid-test_upload_1.txt
Firmware ::   URL: 2025/11/04/guid-test_upload_1.txt
```

### Test 4: Byte Stream with Classification
**Requirements:** None (creates test content in memory)

**What it tests:**
- `UploadImageWithClassification(file_stream, file_name, classification, custom_attributes)` method
- Classification rotation (defect, good, anomaly, normal)
- Custom attributes with confidence scores
- MQTT message publishing

**Output:**
```
Firmware :: Test 4: UploadImageWithClassification from byte stream
Firmware :: Upload Success!
Firmware ::   Classification: defect
Firmware ::   URL: 2025/11/04/guid-classified_1.txt
Firmware ::   MQTT Published: True
```

## Expected Results

When tests run successfully, you should see:

1. **Console Output**: Detailed test results with success/failure status
2. **S3 Uploads**: Files uploaded to the configured S3 bucket
3. **MQTT Messages**: Classification messages published to the file upload topic
4. **SDK Debug Logs**: Detailed upload process logs (if `IsDebug: True`)

## Verification Steps

### 1. Verify S3 Uploads

Check your S3 bucket for uploaded files:
```bash
aws s3 ls s3://your-bucket-name/device-uploads/your-device-id/ --recursive
```

Expected structure:
```
device-uploads/
└── your-device-id/
    └── 2025/
        └── 11/
            └── 04/
                ├── guid-test_image.jpg
                ├── guid-test_upload_1.txt
                └── guid-classified_1.txt
```

### 2. Verify MQTT Messages

Monitor the MQTT topic for classification messages:
```bash
# Topic format: $aws/rules/msg_d2c_file/{device-id}/2.1/11
```

Expected message format:
```json
{
  "d": [{
    "d": {
      "url": "2025/11/04/guid-classified_1.txt",
      "c": "defect",
      "confidence": 0.95,
      "model_version": "1.0",
      "test_number": 1
    }
  }]
}
```

### 3. Check IoTConnect Portal

1. Login to IoTConnect portal
2. Navigate to your device
3. Check Live Data for file upload messages
4. Verify file metadata in device history

## Troubleshooting

### "File upload client not initialized"
**Cause:** File upload configuration not in sync response

**Solution:**
- Verify sync response includes `p.fs` configuration
- Check device has certificate-based authentication
- Review sync response in debug logs

### "File not found: test_image.jpg"
**Cause:** Test image doesn't exist

**Solution:**
```bash
# Create or copy a test image
cp any_image.jpg test_image.jpg
```

### "Failed to get IoT credentials"
**Cause:** IoT credential provider error

**Solution:**
- Verify certificate paths are correct
- Check certificates are not expired
- Verify credential provider URL in sync response
- Check network connectivity

### "S3 upload failed: HTTP 403"
**Cause:** Permission denied

**Solution:**
- Check bucket permissions
- Verify cross-account role (if ca=true)
- Review IAM policies

### MQTT not published
**Cause:** Device not connected or topic not configured

**Solution:**
- Verify `readyStatus == True`
- Check sync response includes `p.topics.fu`
- Review MQTT connection logs

## Example Test Session

```bash
$ python sample/iotconnect-sdk-1.0-firmware-python_msg-2_1.py

# ... SDK initialization ...

Firmware :: Attribute got Sync ::
Firmware :: readyStatus == True
Firmware :: Running file upload integration test...

Firmware :: ========== File Upload Test ==========

Firmware :: Test 1: UploadImage from file path
[FileUploadClient] Getting IoT credentials from: https://...
[FileUploadClient] Target bucket: iotc-612324506361, Customer account: False
[FileUploadClient] Uploading to S3: s3://iotc-612324506361/device-uploads/...
[FileUploadClient] Successfully uploaded to S3: device-uploads/...
Firmware :: Upload Success!
Firmware ::   S3 Key: device-uploads/device-id/2025/11/04/guid-test_image.jpg
Firmware ::   Bucket: iotc-612324506361
Firmware ::   URL: 2025/11/04/guid-test_image.jpg

Firmware :: Test 2: UploadImageWithClassification from file path
[FileUploadClient] Successfully uploaded to S3: device-uploads/...
SDK_MQTT_INFO : Publishing to topic...
Firmware :: Upload Success!
Firmware ::   S3 Key: device-uploads/device-id/2025/11/04/guid-test_image.jpg
Firmware ::   URL: 2025/11/04/guid-test_image.jpg
Firmware ::   MQTT Published: True

Firmware :: Test 3: UploadImage from byte stream
[FileUploadClient] Uploading file from stream: test_upload_1.txt
Firmware :: Upload Success!
Firmware ::   S3 Key: device-uploads/device-id/2025/11/04/guid-test_upload_1.txt
Firmware ::   URL: 2025/11/04/guid-test_upload_1.txt

Firmware :: Test 4: UploadImageWithClassification from byte stream
[FileUploadClient] Uploading file from stream: classified_1.txt
Firmware :: Upload Success!
Firmware ::   Classification: defect
Firmware ::   URL: 2025/11/04/guid-classified_1.txt
Firmware ::   MQTT Published: True

Firmware :: ========== File Upload Test Complete ==========

Firmware :: File upload test completed. Continuing with telemetry...

# ... Normal telemetry continues ...
```

## Performance Testing

To test with larger files or higher frequency:

### Test Large Files
```python
# Create a 10MB test file
with open("large_test.jpg", "wb") as f:
    f.write(os.urandom(10 * 1024 * 1024))

# Upload it
result = sdk.UploadImage(file_path="large_test.jpg")
```

### Test High Frequency
```python
# Change loop interval to 1 (every 10 seconds)
if loop_counter % 1 == 0:
    testFileUpload(Sdk)
```

### Measure Upload Time
```python
import time

start = time.time()
result = sdk.UploadImage(file_path="test_image.jpg")
end = time.time()

print("Upload time: {:.2f} seconds".format(end - start))
```

## Integration with Image Classification

To integrate with actual image classification pipeline:

```python
def classifyImage(image_path):
    """Your ML classification logic here"""
    # Example: Using TensorFlow, PyTorch, OpenCV, etc.
    classification = "defect"  # Your model's prediction
    confidence = 0.95
    return classification, confidence

# In main loop or callback:
image_path = capture_image()  # Get image from camera
classification, confidence = classifyImage(image_path)

result = sdk.UploadImageWithClassification(
    file_path=image_path,
    classification=classification,
    custom_attributes={
        "confidence": confidence,
        "model": "resnet50",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
)
```

## Best Practices

1. **Error Handling**: Always check `result["success"]` before assuming upload worked
2. **File Cleanup**: Delete local files after successful upload to save space
3. **Rate Limiting**: Don't upload too frequently (respect network/storage limits)
4. **File Size**: Keep files reasonable (<10MB recommended)
5. **Naming**: Use descriptive filenames with timestamps
6. **Logging**: Enable debug mode during development (`IsDebug: True`)

## Support

For issues or questions:
- Review `FILE_UPLOAD_USAGE.md` for API documentation
- Check `FILE_UPLOAD_IMPLEMENTATION_SUMMARY.md` for technical details
- Enable debug logging (`IsDebug: True`)
- Check SDK error messages in console output
