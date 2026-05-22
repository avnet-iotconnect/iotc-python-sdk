# Certificate Rotation - IoTConnect Python SDK

## Overview

The IoTConnect Python SDK supports **automatic X.509 certificate rotation** when the device certificate expires or is near expiry. The platform signals this via the `ce=1` flag in the Device Sync Response.

There are **two renewal flows** depending on the Auth Challenge API response:

| Flow | Trigger | Who generates new key? | Certificate Authority | Use Case |
|------|---------|----------------------|----------------------|----------|
| **Without CSR** | `rn` is empty, `pk` present in Auth response | Server | AWS IoT Core CA (Authority managed) | Platform manages keys & certs |
| **With CSR** | `rn` is non-empty in Auth response | Device (firmware generates CSR) | Custom/Self-signed CA | Device manages keys |

> **Note:** AWS IoT Core Authority certificates always use the **Without CSR** flow. The platform generates both the new private key (`pk`) and new certificate (`dc`) and delivers them in the Auth Challenge response.

---

## Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CERTIFICATE ROTATION FLOW                                  │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌──────────┐          ┌──────────┐          ┌──────────────────┐
    │  Device  │          │   SDK    │          │  IoTConnect Cloud │
    │(Firmware)│          │          │          │                  │
    └────┬─────┘          └────┬─────┘          └────────┬─────────┘
         │                     │                         │
         │                     │  1. Discovery Request   │
         │                     │────────────────────────>│
         │                     │  Discovery Response     │
         │                     │  (bu URL with /cg/GUID) │
         │                     │<────────────────────────│
         │                     │                         │
         │                     │  2. Device Sync Request │
         │                     │────────────────────────>│
         │                     │  Sync Response (ce=1)   │
         │                     │<────────────────────────│
         │                     │                         │
         │                     │  ┌─────────────────┐    │
         │                     │  │ Detect ce=1     │    │
         │                     │  │ Start renewal   │    │
         │                     │  │ in background   │    │
         │                     │  └────────┬────────┘    │
         │                     │           │             │
         │                     │  3. Auth Challenge      │
         │                     │  POST /x509/auth        │
         │                     │────────────────────────>│
         │                     │  Auth Response          │
         │                     │  (rn, cId, url, pk, dc) │
         │                     │<────────────────────────│
         │                     │           │             │
         │                     │  ┌────────┴────────┐    │
         │                     │  │ Check rn field  │    │
         │                     │  └──┬──────────┬───┘    │
         │                     │     │          │        │
         │              ┌──────┴─────┴──────┐  ┌┴───────────────────┐
         │              │ rn = empty        │  │ rn = non-empty     │
         │              │ WITHOUT CSR FLOW  │  │ WITH CSR FLOW      │
         │              │ (AWS Authority)   │  │ (Custom CA)        │
         │              └──────┬────────────┘  └┬───────────────────┘
         │                     │                │
         │      (See Without CSR Flow)   (See With CSR Flow)
         │                     │                │
         └─────────────────────┴────────────────┘
```

---

## Without CSR Flow (AWS IoT Core Authority Certificates)

When the Auth Challenge response has an **empty `rn`** and contains `pk` (private key) + `dc` (certificate), the platform has already generated the new credentials. This is the standard flow for **AWS IoT Core Authority managed certificates**.

**No firmware callback is needed. The SDK handles everything automatically.**

```
    ┌──────────┐          ┌──────────┐          ┌──────────────────┐
    │  Device  │          │   SDK    │          │  IoTConnect Cloud │
    │(Firmware)│          │          │          │  (AWS Authority)  │
    └────┬─────┘          └────┬─────┘          └────────┬─────────┘
         │                     │                         │
         │                     │  Auth Response:         │
         │                     │  rn = ""                │
         │                     │  pk = <new key hex>     │
         │                     │  dc = <new cert hex>    │
         │                     │  url = <ack_url>        │
         │                     │  ackId = "<guid>"       │
         │                     │<────────────────────────│
         │                     │                         │
         │                     │  ┌─────────────────┐    │
         │                     │  │ 1. Install pk   │    │
         │                     │  │    (new key)    │    │
         │                     │  │ 2. Install dc   │    │
         │                     │  │    (new cert)   │    │
         │                     │  └────────┬────────┘    │
         │                     │           │             │
         │                     │  3. Disconnect MQTT     │
         │                     │           │             │
         │                     │  4. Reconnect with      │
         │                     │     new cert + key      │
         │                     │────────────────────────>│
         │                     │  Connected ✓            │
         │                     │<────────────────────────│
         │                     │                         │
         │                     │  5. ACK Request         │
         │                     │  GET /x509/cert/ack     │
         │                     │  Headers: cid, dip,     │
         │                     │           ackId         │
         │                     │────────────────────────>│
         │                     │  ACK Response (200)     │
         │                     │<────────────────────────│
         │                     │                         │
         │                     │  6. Re-sync attributes  │
         │                     │  (mt:201)               │
         │                     │────────────────────────>│
         │                     │                         │
         │  Data publish resumes ✓                       │
         │<────────────────────│                         │
         │                     │                         │
```

### Key Points - Without CSR Flow
- **Fully automatic** — no firmware code required
- AWS IoT Core generates both the new private key and certificate
- Old private key is backed up to `{key_path}.bak`
- SDK installs new key first, then new cert, then reconnects
- After successful reconnect, SDK sends ACK and re-syncs attributes

---

## With CSR Flow (Custom/Self-Signed CA Certificates)

When the Auth Challenge response has a **non-empty `rn`** (random number), the device must generate a CSR and sign it to prove identity. This flow is used with **custom or self-signed CA certificates** where the device manages its own keys.

**Firmware must implement the `OnCertSignedRequestCallback` callback.**

```
    ┌──────────┐          ┌──────────┐          ┌──────────────────┐
    │  Device  │          │   SDK    │          │  IoTConnect Cloud │
    │(Firmware)│          │          │          │  (Custom CA)      │
    └────┬─────┘          └────┬─────┘          └────────┬─────────┘
         │                     │                         │
         │                     │  Auth Response:         │
         │                     │  rn = "THPPM82K"       │
         │                     │  cId = "<company_id>"  │
         │                     │  url = "<sign_url>"    │
         │                     │<────────────────────────│
         │                     │                         │
         │  Callback invoked:  │                         │
         │  OnCertSignedRequest│                         │
         │  (rn, device_id,   │                         │
         │   company_id)       │                         │
         │<────────────────────│                         │
         │                     │                         │
         │  ┌────────────────────────────────────┐       │
         │  │ FIRMWARE RESPONSIBILITY:           │       │
         │  │                                    │       │
         │  │ 1. Load current device private key │       │
         │  │ 2. Generate CSR (CN = cpId-uid)    │       │
         │  │    signed with device private key  │       │
         │  │ 3. Sign (RN + CID + CSR_DER)      │       │
         │  │    with device private key         │       │
         │  │ 4. Return {csr, sig, fmt}          │       │
         │  └────────────────────────────────────┘       │
         │                     │                         │
         │  Return:            │                         │
         │  {csr: hex,         │                         │
         │   sig: hex,         │                         │
         │   fmt: "hex"}       │                         │
         │────────────────────>│                         │
         │                     │                         │
         │                     │  4. Sign Request        │
         │                     │  POST <sign_url>        │
         │                     │  {csr, sig, fmt}        │
         │                     │────────────────────────>│
         │                     │  Sign Response:         │
         │                     │  dc = <new cert hex>    │
         │                     │  url = <ack_url>        │
         │                     │  ackId = "<guid>"       │
         │                     │<────────────────────────│
         │                     │                         │
         │                     │  ┌─────────────────┐    │
         │                     │  │ 5. Install new  │    │
         │                     │  │    cert (dc)    │    │
         │                     │  │    Same key!    │    │
         │                     │  └────────┬────────┘    │
         │                     │           │             │
         │                     │  6. Disconnect MQTT     │
         │                     │           │             │
         │                     │  7. Reconnect with      │
         │                     │     new cert + same key │
         │                     │────────────────────────>│
         │                     │  Connected ✓            │
         │                     │<────────────────────────│
         │                     │                         │
         │                     │  8. ACK Request         │
         │                     │  GET /x509/cert/ack     │
         │                     │  Headers: cid, dip,     │
         │                     │           ackId         │
         │                     │────────────────────────>│
         │                     │  ACK Response (200)     │
         │                     │<────────────────────────│
         │                     │                         │
         │                     │  9. Re-sync attributes  │
         │                     │  (mt:201)               │
         │                     │────────────────────────>│
         │                     │                         │
         │  Data publish resumes ✓                       │
         │<────────────────────│                         │
         │                     │                         │
```

### Key Points - With CSR Flow
- Firmware must register `onCertSignedRequest` callback
- Device keeps the **same private key** — only the certificate is renewed
- CSR Common Name (CN) must be `cpId-uniqueId`
- Signature format: `RSA_PKCS1v15_SHA256(RN_bytes + CID_bytes + CSR_DER_bytes)`

---

## API Reference

### 1. Auth Challenge API

**Endpoint:** `POST {identity_url}/api/2.1/agent/x509/auth`

The `identity_url` is automatically extracted from the Discovery Response `bu` field (scheme + host + port).

**Request:**
```json
{
    "companyGuid": "A8E2A84A-ADD9-4E90-8202-C59FAD02520E",
    "cpId": "gg08oct",
    "uniqueId": "enb-06may26-cas02",
    "fmt": "pem",
    "cert": "<hex-encoded DER of current device certificate>"
}
```

**Response (With CSR — Custom CA):**
```json
{
    "d": {
        "ec": 0,
        "ct": 200,
        "cm": {
            "cmt": 1,
            "d": {
                "rn": "2PRLK8EG",
                "cId": "e79439f2-2422-4a7f-bd06-6e8421ab51f3",
                "url": "http://.../api/v2.1/agent/x509/cert/sign"
            }
        }
    },
    "status": 200,
    "message": "Device auth info loaded successfully."
}
```

**Response (Without CSR — AWS Authority):**
```json
{
    "d": {
        "ec": 0,
        "ct": 200,
        "cm": {
            "cmt": 1,
            "d": {
                "rn": "",
                "dc": "<hex-encoded new certificate>",
                "pk": "<hex-encoded new private key>"
            },
            "url": "http://.../api/v2.1/agent/x509/cert/ack",
            "ackId": "a8e2a84a-..."
        }
    },
    "status": 200,
    "message": "Device auth info loaded successfully."
}
```

### 2. Sign API (With CSR flow only)

**Endpoint:** `POST {url from auth response}`

**Request:**
```json
{
    "csr": "<hex-encoded DER CSR>",
    "fmt": "hex",
    "sig": "<hex-encoded signature>"
}
```

**Signature Generation:**
```
data_to_sign = UTF8_bytes(RN + CID) + CSR_DER_bytes
signature = RSA_PKCS1v15_SHA256_Sign(data_to_sign, device_private_key)
```

**Response:**
```json
{
    "d": {
        "ec": 0,
        "ct": 200,
        "cm": {
            "cmt": 2,
            "d": {
                "dc": "<hex-encoded new certificate>"
            },
            "url": "http://.../api/v2.1/agent/x509/cert/ack",
            "ackId": "a8e2a84a-..."
        }
    },
    "status": 200,
    "message": "X509AuthSuccessfully"
}
```

### 3. ACK API

**Endpoint:** `GET {url from sign/auth response}`

**Headers:**
| Header | Value |
|--------|-------|
| `cid` | cpId (e.g., `gg08oct`) |
| `dip` | uniqueId (e.g., `enb-06may26-cas02`) |
| `ackId` | ackId from sign/auth response |

**Response:**
```json
{
    "d": null,
    "status": 200,
    "message": "Device auth info loaded successfully."
}
```

---

## Firmware Implementation Guide (With CSR Flow Only)

> **Without CSR flow requires NO firmware code.** The SDK handles it entirely.

### Step 1: Register the CSR Callback

```python
from iotconnect import IoTConnectSDK

def OnCertSignedRequestCallback(rn, device_id, company_id):
    """
    Called by SDK when CSR-based certificate renewal is needed.
    
    Args:
        rn: Random number from Auth Challenge
        device_id: cpId-uniqueId (use as CSR Common Name)
        company_id: Company ID from Auth Challenge (cId field)
    
    Returns:
        dict: {"csr": "<hex>", "sig": "<hex>", "fmt": "hex"}
    """
    # ... generate CSR and signature ...
    return {"csr": csr_hex, "sig": sig_hex, "fmt": "hex"}

# Register callback after SDK initialization
with IoTConnectSDK(UniqueId, SdkOptions, DeviceConnectionCallback) as Sdk:
    Sdk.onCertSignedRequest(OnCertSignedRequestCallback)
    # ... rest of device setup ...
```

### Step 2: Implement CSR Generation

```python
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

def OnCertSignedRequestCallback(rn, device_id, company_id):
    # 1. Load current device private key
    with open(key_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)
    
    # 2. Build CSR with CN = device_id (cpId-uniqueId)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"GB"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"London"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"London"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Global Security"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, u"IT Department"),
        x509.NameAttribute(NameOID.COMMON_NAME, device_id),
    ])
    
    csr = x509.CertificateSigningRequestBuilder() \
        .subject_name(subject) \
        .sign(private_key, hashes.SHA256(), default_backend())
    
    # 3. Get CSR in DER format -> hex
    csr_der = csr.public_bytes(serialization.Encoding.DER)
    csr_hex = csr_der.hex().upper()
    
    # 4. Generate signature: Sign(RN + CID + CSR_DER) with device key
    rn_cid_bytes = (rn + company_id).encode('utf-8')
    data_to_sign = rn_cid_bytes + csr_der
    
    signature = private_key.sign(
        data_to_sign,
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    sig_hex = signature.hex().upper()
    
    return {"csr": csr_hex, "sig": sig_hex, "fmt": "hex"}
```

### Step 3: Dependencies

```bash
pip install cryptography
```

---

## SDK Configuration (SdkOptions)

No special configuration is needed for certificate rotation. The SDK automatically:

1. Extracts the **identity URL** from the Discovery Response `bu` field
2. Extracts the **companyGuid** from the Discovery Response `bu` URL path (`/cg/{guid}`)
3. Reads the device certificate from `SdkOptions["certificate"]["SSLCertPath"]`
4. Reads the private key from `SdkOptions["certificate"]["SSLKeyPath"]`

```python
SdkOptions = {
    "certificate": {
        "SSLKeyPath": "/path/to/pk_device.pem",
        "SSLCertPath": "/path/to/cert_device.crt",
        "SSLCaPath": "/path/to/AmazonRootCA.pem"
    },
    "discoveryUrl": "https://discovery.iotconnect.io",
    "cpid": "your_cpid",
    "env": "your_env",
    "pf": "aws",
    "IsDebug": True
}
```

---

## File Changes During Renewal

| File | Without CSR (AWS Authority) | With CSR (Custom CA) |
|------|----------------------------|---------------------|
| `cert_device.crt` | Overwritten with new cert from `dc` | Overwritten with new cert from Sign API |
| `pk_device.pem` | Overwritten with new key from `pk` | **No change** (same key used for CSR) |
| `pk_device.pem.bak` | Backup of old key | Not created |

---

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| `KEY_VALUES_MISMATCH` | Private key doesn't match certificate | Without CSR: ensure `pk` is installed before `dc`. With CSR: key should not change |
| `SignatureNotValid` | Wrong signature format | Verify: `Sign(RN + CID + CSR_DER)` with PKCS1v15 + SHA256 |
| `companyGuid validation failed` | Empty companyGuid | SDK extracts from discovery `bu` URL `/cg/{guid}` |
| `Identity URL not found` | Can't resolve auth endpoint | SDK extracts host:port from discovery `bu` URL |
| `No CSR callback registered` | Firmware didn't register callback | Call `Sdk.onCertSignedRequest(callback)` before device connects |
| `Data Publish Fail` after renewal | Attributes not re-synced | SDK auto-sends `mt:201` after reconnect |
| `Auth Challenge error code 3` | Sign API returned error | Check CSR CN matches `cpId-uniqueId` format |

---

## Console Log Colors

When `IsDebug: True`, logs are color-coded:

| Color | Source | Prefix |
|-------|--------|--------|
| 🟢 Green | SDK | `SDK_INFO :` |
| 🔴 Red | SDK Errors | `SDK_ERROR :` |
| 🔵 Blue | Firmware | `Firmware ::` |
| 🔴 Red | Firmware Errors | `Firmware :: ERROR ::` |
| 🟢 Green | MQTT | `SDK_MQTT_INFO :` |

---

## Summary

| Feature | Without CSR (AWS Authority) | With CSR (Custom CA) |
|---------|----------------------------|---------------------|
| Firmware code needed | ❌ None | ✅ Callback required |
| Key management | Platform generates new key | Device keeps same key |
| Certificate Authority | AWS IoT Core CA | Custom/Self-signed CA |
| Auth response contains | `pk` + `dc` | `rn` + `cId` + `url` |
| Private key changes | ✅ Yes (new key from server) | ❌ No (same key) |
| SDK handles automatically | ✅ Fully automatic | ✅ After callback returns |
