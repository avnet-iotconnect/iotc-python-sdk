from awsclient import sigv4_sign, REGION
import requests


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
