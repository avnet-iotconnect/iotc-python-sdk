#!/usr/bin/env python3
"""
POC: Use AWS IoT device certificate -> get temp creds -> STS AssumeRole (cross account) -> PUT to S3
No AWS SDK used (only requests + stdlib).
"""

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import uuid
from urllib.parse import urlencode

import requests

# --------------- CONFIG: FILL THESE ---------------

REGION               = "us-east-1"  # region for STS/S3 (use your region)
IOT_CRED_ENDPOINT    = "c1x1ly2rjmzjow.credentials.iot.us-east-1.amazonaws.com"  # from `aws iot describe-endpoint --endpoint-type iot:CredentialProvider`
IOT_ROLE_ALIAS       = "TempDeviceAlias"        # IoT Role Alias name (case sensitive)
IOT_THING_NAME       = "e3333b0bc58e467bbd1904c0487a14e2-TestDevice2108"        # optional header but required if policies use thing variables
DEVICE_CERT_PEM      = "/home/yash/sdk/cert_TestDevice2108.crt"  # path to device certificate PEM
DEVICE_PRIVATE_KEY   = "/home/yash/sdk/pk_TestDevice2108.pem"
AMAZON_ROOT_CA_PEM   = "/home/yash/sdk/AmazonRootCA1.pem"  # https://www.amazontrust.com/repository/AmazonRootCA1.pem

# Cross-account role to assume
TARGET_ROLE_ARN      = "arn:aws:iam::891377397491:role/allow-sharable-role-891377397491-us-east-1"
ROLE_SESSION_NAME    = f"iot-xaccount-{uuid.uuid4().hex[:8]}"

# S3 upload target (in target account)
S3_BUCKET            = "root-891377397491"
S3_KEY               = "test_poc/TestDevice2108-certificates.zip"
LOCAL_FILE_TO_UPLOAD = "/home/yash/sdk/TestDevice2108-certificates.zip"

# --------------- HELPERS ---------------

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

def sigv4_sign(method, service, region, host, canonical_uri, query_params, headers, payload_bytes, access_key, secret_key, session_token=None, amz_date=None):
    """
    Returns: (headers_with_auth)
    Builds SigV4 Authorization header for the given request.
    """
    if amz_date is None:
        now = dt.datetime.utcnow()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = amz_date[:8]

    # Ensure required headers
    headers = {k.lower(): v.strip() for k, v in headers.items()}
    headers['host'] = host
    headers['x-amz-date'] = amz_date
    if session_token:
        headers['x-amz-security-token'] = session_token

    # Canonical query
    canonical_querystring = urlencode(sorted(query_params.items())) if query_params else ""

    # Canonical headers & signed headers
    canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
    signed_headers = ";".join(sorted(headers))

    payload_hash = _sha256_hex(payload_bytes)

    canonical_request = "\n".join([
        method,
        canonical_uri,
        canonical_querystring,
        canonical_headers,
        signed_headers,
        payload_hash
    ])

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        algorithm,
        amz_date,
        credential_scope,
        _sha256_hex(canonical_request.encode("utf-8"))
    ])

    k_date = _hmac(("AWS4" + secret_key).encode("utf-8"), datestamp)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"{algorithm} "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    # Return headers including Authorization (preserve original case as much as possible)
    final_headers = {k: v for k, v in headers.items()}
    final_headers['Authorization'] = authorization
    final_headers['x-amz-content-sha256'] = payload_hash
    return final_headers

# --------------- STEP 1: Get temp creds from IoT credential provider ---------------

def get_iot_credentials():
    """
    mTLS GET to:
      https://{endpoint}/role-aliases/{roleAlias}/credentials
    header: x-amzn-iot-thingname: <ThingName>   (only needed if policies use thing variables)
    Returns dict with accessKeyId, secretAccessKey, sessionToken, expiration
    """
    url = f"https://{IOT_CRED_ENDPOINT}/role-aliases/{IOT_ROLE_ALIAS}/credentials"
    headers = {}
    if IOT_THING_NAME:
        headers["x-amzn-iot-thingname"] = IOT_THING_NAME

    resp = requests.get(
        url,
        headers=headers,
        cert=(DEVICE_CERT_PEM, DEVICE_PRIVATE_KEY),
        verify=AMAZON_ROOT_CA_PEM,  # server authentication
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    return data["credentials"]

# --------------- STEP 2: Assume target cross-account role with STS ---------------

def assume_role(sts_creds_from_iot):
    """
    SigV4-signed POST to STS regional endpoint: https://sts.{region}.amazonaws.com/
    Body: Action=AssumeRole&RoleArn=...&RoleSessionName=...&Version=2011-06-15
    """
    method = "POST"
    service = "sts"
    host = f"sts.{REGION}.amazonaws.com"
    endpoint = f"https://{host}/"
    canonical_uri = "/"
    query_params = {}  # POST with form body

    body_dict = {
        "Action": "AssumeRole",
        "RoleArn": TARGET_ROLE_ARN,
        "RoleSessionName": ROLE_SESSION_NAME,
        "Version": "2011-06-15"
    }
    body = urlencode(body_dict)
    payload_bytes = body.encode("utf-8")

    headers = {
        "content-type": "application/x-www-form-urlencoded; charset=utf-8"
    }

    h = sigv4_sign(
        method=method,
        service=service,
        region=REGION,
        host=host,
        canonical_uri=canonical_uri,
        query_params=query_params,
        headers=headers,
        payload_bytes=payload_bytes,
        access_key=sts_creds_from_iot["accessKeyId"],
        secret_key=sts_creds_from_iot["secretAccessKey"],
        session_token=sts_creds_from_iot["sessionToken"],
    )

    resp = requests.post(endpoint, data=body, headers=h, timeout=30)
    resp.raise_for_status()

    print("RESPONSE TEXT BASCIALLY : : : : :",resp.text)
    # STS returns XML; simple parse to pull creds
    from xml.etree import ElementTree as ET
    root = ET.fromstring(resp.text)
    ns = {"sts": "https://sts.amazonaws.com/doc/2011-06-15/"}
    # Robust search across no-namespace responses too
    for elem in root.iter():
        if '}' in elem.tag:
            elem.tag = elem.tag.split('}', 1)[1]

    access_key_id     = root.findtext('.//AccessKeyId')
    secret_access_key = root.findtext('.//SecretAccessKey')
    session_token     = root.findtext('.//SessionToken')
    expiration        = root.findtext('.//Expiration')


    return {
        "accessKeyId": access_key_id,
        "secretAccessKey": secret_access_key,
        "sessionToken": session_token,
        "expiration": expiration,
    }

# --------------- STEP 3: Upload to S3 with SigV4 ---------------

def put_s3_object(assumed_role_creds, bucket, key, file_path):
    method = "PUT"
    service = "s3"
    host = f"{bucket}.s3.{REGION}.amazonaws.com"
    canonical_uri = "/" + "/".join([p for p in key.split("/") if p])  # normalize

    with open(file_path, "rb") as f:
        payload_bytes = f.read()

    headers = {
        "content-type": "application/octet-stream"
    }

    h = sigv4_sign(
        method=method,
        service=service,
        region=REGION,
        host=host,
        canonical_uri=canonical_uri,
        query_params={},
        headers=headers,
        payload_bytes=payload_bytes,
        access_key=assumed_role_creds["accessKeyId"],
        secret_key=assumed_role_creds["secretAccessKey"],
        session_token=assumed_role_creds["sessionToken"],
    )

    url = f"https://{host}{canonical_uri}"
    resp = requests.put(url, headers=h, data=payload_bytes, timeout=60)
    resp.raise_for_status()
    return resp.status_code

# --------------- MAIN ---------------

def main():
    print("Step 1: Requesting credentials from IoT credentials provider (mTLS)...")
    iot_creds = get_iot_credentials()
    print(f"  Got creds valid until: {iot_creds['expiration']}")
    print("iot credentials : : : ", iot_creds)
    print("Step 2: Assuming cross-account role via STS...")
    xacct = assume_role(iot_creds)
    if not xacct["accessKeyId"]:
        print("Failed to parse STS credentials", file=sys.stderr)
        sys.exit(2)
    print(f"  Got x-account creds valid until: {xacct['expiration']}")

    print("Step 3: Uploading file to S3 (SigV4 PUT)...")

    print("assumerole credentials : : : ", xacct)

    status = put_s3_object(xacct, S3_BUCKET, S3_KEY, LOCAL_FILE_TO_UPLOAD)
    print(f"  Upload complete. HTTP {status}")
    print(f"s3://{S3_BUCKET}/{S3_KEY}")

if __name__ == "__main__":
    main()
