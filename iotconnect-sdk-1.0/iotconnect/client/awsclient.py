import requests
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import uuid
from urllib.parse import urlencode


REGION = "us-east-1"  # region for STS/S3 (use your region)


def get_aws_credentials(uid, cacert, devicecert, devicekey, aws_credential_endpoint):

    try:
        
        response = requests.get(
           
            url = aws_credential_endpoint,
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



