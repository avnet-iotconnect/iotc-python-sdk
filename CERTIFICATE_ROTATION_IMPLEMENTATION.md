# Certificate Rotation Implementation for IoTConnect Python SDK v2.1

## Overview

This document describes the certificate rotation feature implementation that enables automatic renewal of X.509 certificates for devices connected to IoTConnect.

## Flow Diagram

```
Firmware → SDK → IoTConnect REST API → SDK → Firmware
```

### Detailed Flow

1. **Firmware boots and initializes SDK** with the (expired) certificate
2. **SDK performs Device Sync** (REST call) to `/api/2.1/agent/device-identity/cg/{companyGuid}/uid/{uid}`
3. **IoTConnect validates request** and returns `meta.ce` in sync response:
   - `ce = 0`: Certificate OK
   - `ce = 1`: Certificate Expired
   - `ce = 2`: Certificate Renewal Required
4. **If `meta.ce > 0`**, SDK checks if firmware has registered `onCertReceived` callback:
   - ✅ **Callback registered**: Proceed to step 5
   - ❌ **No callback**: Log warning and skip rotation (backward compatible)
5. **SDK calls auth challenge endpoint** to request new certificates
6. **Auth challenge API** returns new certificate and private key in DER Hex format
7. **SDK passes certificates to Firmware** via `onCertReceivedCallback`
8. **Firmware processes certificates**:
   - Converts DER Hex to PEM format
   - Backs up old certificates
   - Saves new certificates to secure storage
   - Verifies device connectivity
9. **Firmware sends ACK** to SDK by calling `certReceiveAck`
10. **SDK sends ACK** back to IoTConnect API

```
┌─────────────────────────────────────────────────────────────────┐
│ Certificate Expiry Detected (meta.ce > 0)                       │
└─────────────────┬───────────────────────────────────────────────┘
                  │
                  ▼
         ┌────────────────────┐
         │ Is onCertReceived  │
         │ callback registered?│
         └────────┬───────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
       YES                 NO
        │                   │
        ▼                   ▼
┌───────────────┐   ┌──────────────────┐
│ Call Auth     │   │ Log Warning &    │
│ Challenge API │   │ Skip Rotation    │
│               │   │ (Backward Compat)│
└───────┬───────┘   └──────────────────┘
        │
        ▼
┌───────────────┐
│ Receive New   │
│ Certificates  │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ Call Firmware │
│ Callback      │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ Firmware      │
│ Installs Certs│
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ Send ACK to   │
│ IoTConnect    │
└───────────────┘
```

## Implementation Details

### SDK Changes (IoTConnectSDK.py)

#### 1. New Class Variables (Lines 129-130)
```python
_listner_cert_callback = None
_auth_challenge_response = None
```

#### 2. Callback Registration Method (Lines 283-285)
```python
def onCertReceived(self, callback):
    """Register callback for certificate rotation"""
    if callback:
        self._listner_cert_callback = callback
```

#### 3. Certificate Expiry Check (Lines 588-594)
```python
# Check for certificate expiry in process_sync method
if self.has_key(response, "meta") and self.has_key(response["meta"], "ce"):
    ce_status = response["meta"]["ce"]
    if ce_status > 0:
        self.print_debuglog("Certificate expiry detected (ce={}), calling auth challenge...".format(ce_status), 0)
        self.call_auth_challenge()
```

#### 4. Auth Challenge Method (Lines 218-310)
- **First checks if firmware has registered the callback** - if not, skips the entire process
- Reads current device certificate
- Converts certificate to DER Hex format
- **Extracts `companyGuid` from `self._base_url`** (format: `.../device-identity/cg/{companyGuid}/uid/{uid}`)
- Makes POST request to auth challenge endpoint: `{baseurl}/a2.1/agent/x509/auth`
- Parses response to extract:
  - `dc`: Device certificate in DER Hex
  - `pk`: Private key in DER Hex
  - `url`: ACK endpoint URL
  - `ackId`: Acknowledgment ID
- Calls firmware callback with new certificates

**Safety Check:**
```python
# Check if firmware has registered certificate callback
if not self._listner_cert_callback:
    self.print_debuglog("Certificate rotation skipped - No onCertReceived callback registered in firmware", 1)
    return None
```

This prevents unnecessary API calls if the firmware hasn't implemented the certificate rotation callback.

**API Endpoint:**
```
POST {baseurl}/a2.1/agent/x509/auth
Content-Type: application/json-patch+json

{
  "companyGuid": "{companyGuid - extracted from base_url}",
  "cpId": "{cpid}",
  "uniqueId": "{uniqueId}",
  "fmt": "hex",
  "cert": "{DER Hex format device certificate}"
}
```

**CompanyGuid Extraction:**
The `companyGuid` is extracted from the sync base URL:
- Base URL format: `https://example.iotconnect.io/api/2.1/agent/device-identity/cg/{companyGuid}/uid/{uid}`
- SDK extracts the GUID from between `/cg/` and `/uid/`
- Example: If base URL is `.../cg/12345678-abcd-1234-abcd-1234567890ab/uid/...`
- Then `companyGuid = "12345678-abcd-1234-abcd-1234567890ab"`

#### 5. Certificate ACK Method (Lines 1183-1233)
```python
def certReceiveAck(self, ackId, status=True, msg="Certificate installed successfully"):
    """Send ACK to IoTConnect after certificate installation"""
```

**API Endpoint:**
```
GET {url from auth response}
Content-Type: application/json-patch+json
Headers:
  - cid: {ackId}
  - dip: {uniqueId}

Body:
{
  "version": "2.1"
}
```

### Utility Functions (util.py)

#### 1. DER Hex to PEM Conversion (Lines 264-297)
```python
def der_hex_to_pem(der_hex, cert_type="CERTIFICATE"):
    """Convert DER hex string to PEM format"""
```

#### 2. Save PEM File (Lines 299-317)
```python
def save_pem_file(pem_data, file_path):
    """Save PEM data to a file"""
```

#### 3. Convert and Save Certificates (Lines 319-357)
```python
def convert_and_save_certificates(dc_hex, pk_hex, cert_path, key_path):
    """Convert DER hex certificates to PEM and save to files"""
```

### SDK Reconnection Method (IoTConnectSDK.py)

#### reconnect_with_new_certificates Method (Lines 1204-1257)
```python
def reconnect_with_new_certificates(self, cert_path, key_path, timeout=30):
    """
    Disconnect and reconnect MQTT with new certificates

    Args:
        cert_path: Path to new certificate file
        key_path: Path to new key file
        timeout: Maximum time to wait for reconnection (seconds)

    Returns:
        True if reconnection successful, False otherwise
    """
```

**The method performs:**
1. Disconnects from current MQTT broker
2. Updates certificate paths in SDK config
3. Reinitializes MQTT client with new certificates
4. Waits for successful reconnection (with timeout)
5. Returns True if connected, False otherwise

**Error Logs:**
- `[INFO_CE06]`: Disconnecting for certificate rotation
- `[INFO_CE07]`: Successfully reconnected with new certificates
- `[ERR_CE08]`: Failed to reconnect within timeout
- `[ERR_CE09]`: Reconnection exception

### Firmware Implementation (iotconnect-sdk-1.0-firmware-python_msg-2_1.py)

#### Certificate Rotation Callback (Lines 232-380)
```python
def onCertReceivedCallback(cert_data):
    """
    Certificate Rotation Callback

    Args:
        cert_data: Dictionary containing:
            - dc: Device certificate in DER Hex format
            - pk: Private key in DER Hex format
            - ackId: Acknowledgment ID
    """
```

**The callback performs:**
1. Extracts certificate data (dc, pk, ackId)
2. Backs up old certificates with timestamp
3. Converts DER Hex to PEM format using `util.der_hex_to_pem()`
4. Saves new certificates to file system
5. **Disconnects from MQTT broker**
6. **Reconnects with new certificates** using `Sdk.reconnect_with_new_certificates()`
7. **Verifies connection success**
8. If successful:
   - Sends ACK to SDK via `Sdk.certReceiveAck()`
   - Cleans up backup certificates
9. If failed:
   - Restores old certificates from backup
   - Attempts to reconnect with old certificates
   - Sends failure ACK

#### Callback Registration (Line 390)
```python
Sdk.onCertReceived(onCertReceivedCallback)
```

## Quick Reference: Two Scenarios

### Scenario A: Firmware WITH Certificate Rotation Support ✅
```python
# Firmware has registered the callback
Sdk.onCertReceived(onCertReceivedCallback)

# When meta.ce > 0:
# ✓ SDK detects certificate expiry
# ✓ SDK checks callback - FOUND
# ✓ SDK calls auth challenge API
# ✓ SDK receives new certificates
# ✓ SDK calls firmware callback
# ✓ Firmware installs certificates
# ✓ Firmware sends ACK
# Result: Certificate rotation completed successfully
```

### Scenario B: Firmware WITHOUT Certificate Rotation Support ❌
```python
# Firmware has NOT registered the callback
# (Old firmware or firmware that doesn't support rotation)

# When meta.ce > 0:
# ✓ SDK detects certificate expiry
# ✗ SDK checks callback - NOT FOUND
# ⚠ SDK logs warning: "Certificate rotation skipped - No callback registered"
# ✗ SDK skips auth challenge API call
# Result: No rotation, backward compatible, no errors
```

## Usage Example

### 1. Firmware Setup
```python
from iotconnect import IoTConnectSDK

# Initialize SDK
SdkOptions = {
    "certificate": {
        "SSLKeyPath": "path/to/device.key",
        "SSLCertPath": "path/to/device.crt",
        "SSLCaPath": "path/to/rootCA.pem"
    },
    # ... other options
}

with IoTConnectSDK(UniqueId, SdkOptions, DeviceConectionCallback) as Sdk:
    # Register certificate rotation callback
    Sdk.onCertReceived(onCertReceivedCallback)

    # Continue normal operations
```

### 2. Certificate Rotation Callback Implementation
```python
def onCertReceivedCallback(cert_data):
    from iotconnect.common.util import util

    dc_hex = cert_data["dc"]
    pk_hex = cert_data["pk"]
    ack_id = cert_data["ackId"]

    # Backup old certificates
    backup_cert = "device.crt.backup"
    backup_key = "device.key.backup"
    shutil.copy2("path/to/device.crt", backup_cert)
    shutil.copy2("path/to/device.key", backup_key)

    # Convert and save new certificates
    cert_pem = util.der_hex_to_pem(dc_hex, "CERTIFICATE")
    key_pem = util.der_hex_to_pem(pk_hex, "PRIVATE KEY")
    util.save_pem_file(cert_pem, "path/to/device.crt")
    util.save_pem_file(key_pem, "path/to/device.key")

    # Disconnect and reconnect with new certificates
    success = Sdk.reconnect_with_new_certificates(
        "path/to/device.crt",
        "path/to/device.key",
        timeout=30
    )

    if success:
        # Send success ACK
        Sdk.certReceiveAck(ack_id, True, "Certificate installed and verified")
    else:
        # Restore old certificates
        shutil.copy2(backup_cert, "path/to/device.crt")
        shutil.copy2(backup_key, "path/to/device.key")
        # Try to reconnect with old certs
        Sdk.reconnect_with_new_certificates("path/to/device.crt", "path/to/device.key")
        # Send failure ACK
        Sdk.certReceiveAck(ack_id, False, "Reconnection failed")
```

## Auth Challenge Response Format

```json
{
  "d": {
    "ec": 0,
    "ct": 200,
    "cm": {
      "cmt": 2,
      "d": {
        "dc": "82035930820241A003020102...",  // Device certificate in DER Hex
        "pk": "308204A50201000282010100..."   // Private key in DER Hex
      },
      "url": "https://example.iotconnect.io/api/v2.1/agent/x509/cert/ack",
      "ackId": "91969f85-952f-4618-87bc-25253313f49e"
    }
  },
  "status": 200,
  "message": "Device auth info loaded successfully."
}
```

## Safety Mechanisms

### Callback Registration Check

**IMPORTANT**: The SDK will **automatically check** if the firmware has registered the `onCertReceived` callback **before** making the auth challenge API call.

**Behavior:**
- ✅ **If callback is registered**: SDK proceeds with certificate rotation flow
- ❌ **If callback is NOT registered**: SDK skips auth challenge and logs a warning

**Benefits:**
1. Prevents unnecessary API calls if firmware doesn't support certificate rotation
2. Avoids wasting network resources
3. Provides clear warning message for debugging
4. Fully backward compatible with existing implementations

**Example Log Output (when callback not registered):**
```
SDK_INFO : Certificate rotation skipped - No onCertReceived callback registered in firmware
[WARN_CE00] 2025-12-02 10:30:45.000 [sid_deviceId] Certificate rotation skipped - Firmware has not registered onCertReceived callback
```

## Error Handling

### SDK Error Logs
- `[WARN_CE00]`: Certificate rotation skipped - No callback registered
- `[INFO_CE01]`: Certificate expiry detected
- `[INFO_CE02]`: Auth challenge response received
- `[INFO_CE02B]`: New certificates passed to firmware callback
- `[ERR_CE03]`: Auth challenge failed
- `[INFO_CE04]`: Certificate ACK sent successfully
- `[ERR_CE05]`: Certificate ACK failed
- `[INFO_CE06]`: Disconnecting for certificate rotation
- `[INFO_CE07]`: Successfully reconnected with new certificates
- `[ERR_CE08]`: Failed to reconnect within timeout
- `[ERR_CE09]`: Reconnection exception

### Firmware Best Practices
1. **Always backup old certificates** before installing new ones
2. **Verify device connectivity** with new certificates before sending ACK
3. **Restore old certificates** if connectivity check fails
4. **Send failure ACK** if installation fails
5. **Handle exceptions gracefully** and log errors

## Testing

### Test Scenario 1: Normal Certificate Rotation ✅
```
1. Device connects with expiring certificate
2. Sync API returns `meta.ce = 1` or `meta.ce = 2`
3. SDK checks callback registration → Found
4. SDK calls auth challenge API
5. SDK receives new certificates (dc, pk, ackId)
6. SDK calls firmware callback
7. Firmware backs up old certificates
8. Firmware saves new certificates
9. Firmware calls Sdk.reconnect_with_new_certificates()
   → MQTT disconnects
   → Config updated with new cert paths
   → MQTT reconnects with new certificates
   → Connection successful
10. Firmware sends success ACK
11. Firmware cleans up backup certificates
Result: ✅ Certificate rotation completed
```

### Test Scenario 2: Installation Failure ❌
```
1-6. Same as Scenario 1
7. Firmware backs up old certificates
8. Firmware attempts to save new certificates → FAILS (disk full)
9. Exception caught
10. Firmware sends failure ACK
Result: ❌ Old certificates remain in place
```

### Test Scenario 3: Reconnection Failure ❌
```
1-8. Same as Scenario 1
9. Firmware calls Sdk.reconnect_with_new_certificates()
   → MQTT disconnects
   → Config updated
   → MQTT attempts reconnect → FAILS (invalid certificate)
   → Timeout reached
   → Returns False
10. Firmware detects reconnection failure
11. Firmware restores old certificates from backup
12. Firmware calls Sdk.reconnect_with_new_certificates() with old certs
   → MQTT reconnects with old certificates → SUCCESS
13. Firmware sends failure ACK
Result: ❌ Rotation failed, device back online with old certs
```

### Test Scenario 4: No Callback Registered ⚠️
```
1. Device connects with expiring certificate
2. Sync API returns `meta.ce = 1` or `meta.ce = 2`
3. SDK checks callback registration → NOT Found
4. SDK logs warning: [WARN_CE00]
5. SDK skips auth challenge
Result: ⚠️ No rotation attempted (backward compatible)
```

### Expected Log Sequence (Success)
```
SDK_INFO : Certificate expiry detected (ce=1), calling auth challenge...
[INFO_CE01] Certificate expiry detected (ce=1)
SDK_INFO : Auth challenge response received
[INFO_CE02] Auth challenge response received
[INFO_CE02B] New certificates passed to firmware callback

Firmware :: Certificate Rotation - New certificates received
Firmware :: Backing up old certificates...
Firmware :: Converting certificates from DER hex to PEM format...
Firmware :: Saving new certificates...
Firmware :: Disconnecting from MQTT broker...

SDK_INFO : Disconnecting from MQTT broker...
[INFO_CE06] Disconnecting for certificate rotation
SDK_INFO : Disconnected successfully
SDK_INFO : Reinitializing MQTT client with new certificates...
SDK_INFO : Device Is Connected with IoTConnect
SDK_INFO : Successfully reconnected with new certificates
[INFO_CE07] Successfully reconnected with new certificates

Firmware :: ✓ Reconnection successful!
Firmware :: ✓ Device is now using new certificates
Firmware :: Sending certificate installation ACK...
SDK_INFO : Certificate ACK sent successfully
[INFO_CE04] Certificate ACK sent

Firmware :: Certificate Rotation Completed Successfully
```

## Security Considerations

1. **Certificate Storage**: Certificates should be stored in secure storage with appropriate permissions
2. **Private Key Protection**: Private keys should never be logged or exposed
3. **Backup Management**: Old certificates should be securely deleted after successful rotation
4. **DER Hex Format**: Certificates are transmitted in DER Hex format for security
5. **ACK Verification**: Always verify certificate installation before sending ACK

## API Endpoints Summary

### 1. Device Sync
- **URL**: `{baseurl}/api/2.1/agent/device-identity/cg/{companyGuid}/uid/{uid}`
- **Method**: GET
- **Response**: Includes `meta.ce` for certificate status

### 2. Auth Challenge
- **URL**: `{baseurl}/a2.1/agent/x509/auth`
- **Method**: POST
- **Headers**: `Content-Type: application/json-patch+json`
- **Body**: `{companyGuid, cpId, uniqueId, fmt: "hex", cert}`

### 3. Certificate ACK
- **URL**: From auth challenge response
- **Method**: GET
- **Headers**: `cid: {ackId}`, `dip: {uniqueId}`
- **Body**: `{version: "2.1"}`

## Files Modified

1. **iotconnect/IoTConnectSDK.py**
   - Added certificate expiry check
   - Added auth challenge method
   - Added certificate ACK method
   - Added callback registration

2. **iotconnect/common/util.py**
   - Added DER Hex to PEM conversion utilities
   - Added certificate save methods

3. **sample/iotconnect-sdk-1.0-firmware-python_msg-2_1.py**
   - Added certificate rotation callback implementation
   - Added callback registration

## Backward Compatibility

This implementation is **fully backward compatible**. If:
- No certificate expiry is detected (`meta.ce = 0`)
- No callback is registered
- Device doesn't support certificate rotation

The SDK will continue to work normally without any changes.

## Version Information

- **SDK Version**: 2.1
- **Implementation Date**: 2025-12-02
- **Python Compatibility**: Python 2.7+ and Python 3.5+

## Support

For issues or questions, please refer to the IoTConnect documentation or contact support.
