"""
IoTConnect File Upload Client
Handles file uploads to AWS S3 using AWS REST API (no SDK)
Supports both IoTConnect S3 bucket and customer account S3 buckets
"""

import sys
import os
import json
import hashlib
import hmac
import base64
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse, quote
import requests
import xml.etree.ElementTree as ET


class FileUploadClient:
    """
    Client for uploading files to S3 via AWS REST API
    Supports IoT Core credential provider and STS assume role
    """

    def __init__(self, unique_id, ca_cert, device_cert, device_key, fs_config, debug=False):
        """
        Initialize file upload client

        Args:
            unique_id: Device unique identifier
            ca_cert: Path to CA certificate
            device_cert: Path to device certificate
            device_key: Path to device private key
            fs_config: File system configuration from sync response (p.fs)
            debug: Enable debug logging
        """
        self.unique_id = unique_id
        self.ca_cert = ca_cert
        self.device_cert = device_cert
        self.device_key = device_key
        self.fs_config = fs_config
        self.debug = debug

        # Parse configuration
        self.buckets = fs_config.get("buckets", [])
        self.credential_url = fs_config.get("url", "")

        if not self.credential_url:
            raise ValueError("File upload credential URL not found in sync response")

        if not self.buckets:
            raise ValueError("No S3 buckets configured in sync response")

    def _log(self, message):
        """Print debug log if debug is enabled"""
        if self.debug:
            print(f"[FileUploadClient] {message}")

    def _get_iot_credentials(self):
        """
        Get temporary AWS credentials from IoT Core credential provider

        Returns:
            tuple: (access_key_id, secret_access_key, session_token)
        """
        url = self.credential_url.strip()

        # Validate URL
        try:
            p = urlparse(url)
            if p.scheme != "https" or not url.endswith("/credentials"):
                raise ValueError(f"Bad credential URL: {url}. URL must use HTTPS and end with '/credentials'")
            if not p.netloc:
                raise ValueError(f"Invalid URL format: {url}. Missing domain name")
        except Exception as e:
            raise ValueError(f"Failed to parse URL '{url}': {e}")

        self._log(f"Getting IoT credentials from: {url}")

        try:
            response = requests.get(
                url=url,
                cert=(self.device_cert, self.device_key),
                verify=self.ca_cert,
                headers={"x-amzn-iot-thingname": self.unique_id},
                timeout=30
            )

            if response.status_code == 200:
                res_data = response.json()
                credentials = res_data.get("credentials", {})
                return (
                    credentials.get("accessKeyId"),
                    credentials.get("secretAccessKey"),
                    credentials.get("sessionToken")
                )
            else:
                self._log(f"Failed to get IoT credentials. Status: {response.status_code}, Response: {response.text}")
                raise Exception(f"Failed to get IoT credentials: HTTP {response.status_code}")

        except requests.RequestException as e:
            self._log(f"Request error while getting IoT credentials: {e}")
            raise Exception(f"Error obtaining IoT credentials: {e}")

    def _assume_cross_account_role(self, iot_access_key, iot_secret_key, iot_session_token, role_arn):
        """
        Assume cross-account role using STS to access customer S3 bucket

        Args:
            iot_access_key: IoT temporary access key
            iot_secret_key: IoT temporary secret key
            iot_session_token: IoT temporary session token
            role_arn: Role ARN to assume (from sync response rarn field)

        Returns:
            tuple: (access_key_id, secret_access_key, session_token)
        """
        self._log(f"Assuming cross-account role: {role_arn}")

        # STS endpoint - using us-east-1 as default
        sts_host = "sts.amazonaws.com"
        sts_endpoint = f"https://{sts_host}/"

        # Generate role session name
        session_name = f"iotc-{self.unique_id}-{int(datetime.now(timezone.utc).timestamp())}"

        # Build STS AssumeRole request parameters
        params = {
            "Action": "AssumeRole",
            "Version": "2011-06-15",
            "RoleArn": role_arn,
            "RoleSessionName": session_name,
            "DurationSeconds": "3600"
        }

        # Sign the request using AWS Signature Version 4
        timestamp = datetime.now(timezone.utc)
        date_stamp = timestamp.strftime('%Y%m%d')
        amz_date = timestamp.strftime('%Y%m%dT%H%M%SZ')

        # Create canonical request
        method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""

        # Build canonical headers
        canonical_headers = f"host:{sts_host}\nx-amz-date:{amz_date}\n"
        if iot_session_token:
            canonical_headers += f"x-amz-security-token:{iot_session_token}\n"

        signed_headers = "host;x-amz-date"
        if iot_session_token:
            signed_headers += ";x-amz-security-token"

        # Build payload
        payload = "&".join([f"{k}={quote(str(v), safe='')}" for k, v in sorted(params.items())])
        payload_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()

        canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

        # Create string to sign
        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/us-east-1/sts/aws4_request"
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"

        # Calculate signature
        def sign(key, msg):
            return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

        k_date = sign(('AWS4' + iot_secret_key).encode('utf-8'), date_stamp)
        k_region = sign(k_date, 'us-east-1')
        k_service = sign(k_region, 'sts')
        k_signing = sign(k_service, 'aws4_request')
        signature = hmac.new(k_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

        # Build authorization header
        authorization_header = f"{algorithm} Credential={iot_access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

        # Make STS request
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "X-Amz-Date": amz_date,
            "Authorization": authorization_header
        }

        if iot_session_token:
            headers["X-Amz-Security-Token"] = iot_session_token

        # self._log(f"Assuming role sts endpoint: {sts_endpoint}")
        # self._log(f"Assuming role Data: {payload}")
        # self._log(f"Assuming role Headers: {headers}")

        try:
            response = requests.post(
                sts_endpoint,
                data=payload,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                # Parse XML response
                root = ET.fromstring(response.content)
                ns = {'sts': 'https://sts.amazonaws.com/doc/2011-06-15/'}

                credentials = root.find('.//sts:Credentials', ns)
                if credentials is not None:
                    access_key = credentials.find('sts:AccessKeyId', ns).text
                    secret_key = credentials.find('sts:SecretAccessKey', ns).text
                    session_token = credentials.find('sts:SessionToken', ns).text

                    self._log("Successfully assumed cross-account role")
                    return (access_key, secret_key, session_token)
                else:
                    raise Exception("Failed to parse STS response: Credentials not found")
            else:
                self._log(f"STS AssumeRole failed. Status: {response.status_code}, Response: {response.text}")
                raise Exception(f"STS AssumeRole failed: HTTP {response.status_code}")

        except requests.RequestException as e:
            self._log(f"Request error during STS AssumeRole: {e}")
            raise Exception(f"Error assuming cross-account role: {e}")

    def _sign_s3_request(self, method, bucket, key, access_key, secret_key, session_token,
                         region="us-east-1", payload=b"", headers=None):
        """
        Sign S3 request using AWS Signature Version 4

        Args:
            method: HTTP method (PUT, GET, etc.)
            bucket: S3 bucket name
            key: S3 object key
            access_key: AWS access key
            secret_key: AWS secret key
            session_token: AWS session token
            region: AWS region
            payload: Request payload bytes
            headers: Additional headers dict

        Returns:
            tuple: (signed_headers_dict, host, url)
        """
        timestamp = datetime.now(timezone.utc)
        date_stamp = timestamp.strftime('%Y%m%d')
        amz_date = timestamp.strftime('%Y%m%dT%H%M%SZ')

        # Build host and URL
        host = f"{bucket}.s3.{region}.amazonaws.com"
        url = f"https://{host}/{key}"

        # Initialize headers
        if headers is None:
            headers = {}

        # Add required headers
        headers["Host"] = host
        headers["X-Amz-Date"] = amz_date

        if session_token:
            headers["X-Amz-Security-Token"] = session_token

        # Calculate content hash
        payload_hash = hashlib.sha256(payload).hexdigest()
        headers["X-Amz-Content-Sha256"] = payload_hash

        # Create canonical request
        canonical_uri = f"/{key}"
        canonical_querystring = ""

        # Sort and format headers
        canonical_headers = ""
        signed_header_names = []
        for header_name in sorted(headers.keys(), key=str.lower):
            canonical_headers += f"{header_name.lower()}:{headers[header_name].strip()}\n"
            signed_header_names.append(header_name.lower())

        signed_headers = ";".join(signed_header_names)

        canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

        # Create string to sign
        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{region}/s3/aws4_request"
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"

        # Calculate signature
        def sign(key, msg):
            return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

        k_date = sign(('AWS4' + secret_key).encode('utf-8'), date_stamp)
        k_region = sign(k_date, region)
        k_service = sign(k_region, 's3')
        k_signing = sign(k_service, 'aws4_request')
        signature = hmac.new(k_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

        # Add authorization header
        headers["Authorization"] = f"{algorithm} Credential={access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

        return headers, host, url

    def _upload_to_s3(self, file_data, file_name, bucket_name, access_key, secret_key, session_token, region="us-east-1"):
        """
        Upload file to S3 using AWS REST API

        Args:
            file_data: File content bytes
            file_name: Name of the file
            bucket_name: S3 bucket name
            access_key: AWS access key
            secret_key: AWS secret key
            session_token: AWS session token
            region: AWS region

        Returns:
            str: S3 object key (path)
        """
        # Generate S3 path: device-uploads/{UniqueId}/{DateTime.UtcNow:yyyy/MM/dd}/{Guid.NewGuid()}-{fileName}
        now = datetime.now(timezone.utc)
        date_path = now.strftime('%Y/%m/%d')
        file_guid = str(uuid.uuid4())
        s3_key = f"device-uploads/{self.unique_id}/{date_path}/{file_guid}-{file_name}"

        self._log(f"Uploading to S3: s3://{bucket_name}/{s3_key}")

        # Determine content type
        content_type = self._get_content_type(file_name)

        # Sign the request
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(file_data))
        }

        signed_headers, host, url = self._sign_s3_request(
            method="PUT",
            bucket=bucket_name,
            key=s3_key,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            region=region,
            payload=file_data,
            headers=headers
        )

        # Upload to S3
        try:
            response = requests.put(
                url,
                data=file_data,
                headers=signed_headers,
                timeout=300  # 5 minutes timeout for large files
            )

            if response.status_code in [200, 201, 204]:
                self._log(f"Successfully uploaded to S3: {s3_key}")
                return s3_key
            else:
                self._log(f"S3 upload failed. Status: {response.status_code}, Response: {response.text}")
                raise Exception(f"S3 upload failed: HTTP {response.status_code} - {response.text}")

        except requests.RequestException as e:
            self._log(f"Request error during S3 upload: {e}")
            raise Exception(f"Error uploading to S3: {e}")

    def _get_content_type(self, file_name):
        """Get MIME content type based on file extension"""
        ext = os.path.splitext(file_name)[1].lower()

        content_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff',
            '.svg': 'image/svg+xml',
            '.pdf': 'application/pdf',
            '.zip': 'application/zip',
            '.tar': 'application/x-tar',
            '.gz': 'application/gzip',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.txt': 'text/plain',
            '.csv': 'text/csv',
            '.log': 'text/plain',
        }

        return content_types.get(ext, 'application/octet-stream')

    def upload_file(self, file_path=None, file_stream=None, file_name=None):
        """
        Upload file to S3

        Args:
            file_path: Path to file (if uploading from file system)
            file_stream: File content as bytes or base64 string (if uploading from memory)
            file_name: Name of file (required if using file_stream)

        Returns:
            dict: Upload result with keys:
                - success: bool
                - s3_key: S3 object key
                - bucket: Bucket name
                - url: URL path for MQTT message
                - error: Error message (if failed)
        """
        try:
            # Validate inputs
            if file_path:
                if not os.path.exists(file_path):
                    raise ValueError(f"File not found: {file_path}")

                # Read file
                with open(file_path, 'rb') as f:
                    file_data = f.read()

                file_name = os.path.basename(file_path)
                self._log(f"Uploading file from path: {file_path}")

            elif file_stream and file_name:
                # Handle file stream
                if isinstance(file_stream, str):
                    # Assume base64 encoded
                    try:
                        file_data = base64.b64decode(file_stream)
                    except Exception as e:
                        raise ValueError(f"Failed to decode base64 stream: {e}")
                elif isinstance(file_stream, bytes):
                    file_data = file_stream
                else:
                    raise ValueError("file_stream must be bytes or base64 string")

                self._log(f"Uploading file from stream: {file_name}")

            else:
                raise ValueError("Either file_path or (file_stream + file_name) must be provided")

            # Get IoT credentials
            iot_access_key, iot_secret_key, iot_session_token = self._get_iot_credentials()

            # Determine target bucket (use first bucket for now, could be made configurable)
            # Priority: ca=false (IoTConnect bucket) first, then ca=true (customer bucket)
            target_bucket = None
            target_bucket_config = None
            is_customer_account = False

            for bucket in self.buckets:
                if not bucket.get("ca", False):
                    target_bucket = bucket.get("bn")
                    target_bucket_config = bucket
                    is_customer_account = False
                    break

            # If no IoTConnect bucket, use customer bucket
            if not target_bucket and len(self.buckets) > 0:
                target_bucket = self.buckets[0].get("bn")
                target_bucket_config = self.buckets[0]
                is_customer_account = self.buckets[0].get("ca", False)

            if not target_bucket:
                raise Exception("No valid S3 bucket found in configuration")

            self._log(f"Target bucket: {target_bucket}, Customer account: {is_customer_account}")

            # Get appropriate credentials
            if is_customer_account:
                # Get role ARN from bucket config
                role_arn = target_bucket_config.get("rarn")
                if not role_arn:
                    raise Exception(f"Role ARN (rarn) not found in bucket configuration for customer account")

                # Assume cross-account role
                access_key, secret_key, session_token = self._assume_cross_account_role(
                    iot_access_key, iot_secret_key, iot_session_token, role_arn
                )
            else:
                # Use IoT credentials directly
                access_key = iot_access_key
                secret_key = iot_secret_key
                session_token = iot_session_token

            # Upload to S3
            s3_key = self._upload_to_s3(
                file_data=file_data,
                file_name=file_name,
                bucket_name=target_bucket,
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token
            )

            # Generate URL path for MQTT message (format: yyyy/MM/dd/guid-filename)
            now = datetime.now(timezone.utc)
            date_path = now.strftime('%Y/%m/%d')
            # Extract the full guid-filename from s3_key (last part after all slashes)
            guid_filename = s3_key.split('/')[-1]
            url_path = f"{date_path}/{guid_filename}"

            return {
                "success": True,
                "s3_key": s3_key,
                "bucket": target_bucket,
                "url": url_path,
                "error": None
            }

        except Exception as e:
            self._log(f"Upload failed: {e}")
            return {
                "success": False,
                "s3_key": None,
                "bucket": None,
                "url": None,
                "error": str(e)
            }
