"""
  ******************************************************************************
  * @file   : iotconnect-sdk-1.0-firmware-python_msg-2_1.py
  * @author : Softweb Solutions An Avnet Company
  * @modify : 07-03-2025
  * @brief  : Firmware part for Python SDK 2.1
  ******************************************************************************
"""

"""
 * Hope you have installed the Python SDK v2.1 as guided in README.md file or from documentation portal. 
 * Import the IoTConnect SDK package and other required packages
"""

import sys
import json
import time
import threading
import random
from iotconnect import IoTConnectSDK
from datetime import datetime, timezone
import os
import subprocess
import hashlib
import binascii

# Enable ANSI color support on Windows
if sys.platform == 'win32':
    os.system('')  # Enables ANSI escape sequences in Windows terminal

# New import: helper to start KVS WebRTC MASTER on device (created earlier)
from iotconnect.client.awskinesisclient import start_kvs_webrtc_from_devicecert

# ANSI color codes for console output
# Blue = Firmware logs, Red = Errors, Green = SDK logs (handled in SDK)
BLUE = "\033[94m"
RED = "\033[91m"
RESET = "\033[0m"

def fw_print(msg):
    """Print firmware log in blue color"""
    print(f"{BLUE}Firmware :: {msg}{RESET}")

def fw_error(msg):
    """Print firmware error in red color"""
    print(f"{RED}Firmware :: ERROR :: {msg}{RESET}")

"""
* ## Prerequisite parameter to run this sampel code
* cpId         :: It need to get from the IoTConnect platform "Settings->Key Vault". 
* uniqueId     :: Its device ID which register on IotConnect platform and also its status has Active and Acquired
* env          :: It need to get from the IoTConnect platform "Settings->Key Vault". 
* interval     :: send data frequency in seconds
* sdkOptions   :: It helps to define the path of self signed and CA signed certificate as well as define the offlinne storage configuration.
"""

UniqueId = "ankit-auto01"

Sdk=None
interval = 10
# add Direct Method
directmethodlist={}
ACKdirect=[]
device_list=[]
readyStatus = False
file_upload_counter = 0
test_file_upload = False  # Set to True to enable file upload testing
test_array_data = False  # Set to True to enable array data testing

"""
* sdkOptions is optional. Mandatory for "certificate" X.509 device authentication type
* "certificate" : It indicated to define the path of the certificate file. Mandatory for X.509/SSL device CA signed or self-signed authentication type only.
* 	- SSLKeyPath: your device key
* 	- SSLCertPath: your device certificate
* 	- SSLCaPath : Root CA certificate
* 	- Windows + Linux OS: Use "/" forward slash (Example: Windows: "E:/folder1/folder2/certificate", Linux: "/home/folder1/folder2/certificate")
* "offlineStorage" : Define the configuration related to the offline data storage 
* 	- disabled : false = offline data storing, true = not storing offline data 
* 	- availSpaceInMb : Define the file size of offline data which should be in (MB)
* 	- fileCount : Number of files need to create for offline data
* "devicePrimaryKey" : It is optional parameter. Mandatory for the Symmetric Key Authentication support only. It gets from the IoTConnect UI portal "Device -> Select device -> info(Tab) -> Connection Info -> Device Connection".
    - - "devicePrimaryKey": "<<your Key>>"
* Note: sdkOptions is optional but mandatory for SSL/x509 device authentication type only. Define proper setting or leave it NULL. If you not provide the offline storage it will set the default settings as per defined above. It may harm your device by storing the large data. Once memory get full may chance to stop the execution.
"""


SdkOptions={
	"certificate" : { 
        # Certs - update paths for your system if required
        "SSLKeyPath"  : "c:/Users/ankit.sangani/Downloads/ankit-auto01-certificates/pk_ankit-auto01.pem",    #aws=pk_devicename.pem
        "SSLCertPath" : "c:/Users/ankit.sangani/Downloads/ankit-auto01-certificates/cert_ankit-auto01.crt",  #aws=cert_devicename.crt
        "SSLCaPath"   : "c:/SW-AnkitSangani/AWS/sdk/AmazonrootCA.pem"     #aws=root-CA.pem
	},
    "offlineStorage":{
        "disabled": False,
	    "availSpaceInMb": 0.01,
	    "fileCount": 5,
        "keepalive":60
    },
     "skipValidation":False,
    # "devicePrimaryKey":"<<DevicePrimaryKey>>",
	# As per your Environment(Azure or Azure EU or AWS) uncomment single URL and commnet("#") rest of URLs.
    # "discoveryUrl":"https://eudiscovery.iotconnect.io" #Azure EU environment 
    "discoveryUrl":"https://discovery.iotconnect.io", #Azure All Environment 
    "IsDebug": True,
    "cpid" : "gg08oct02",
    "sId" : "",
    "env" : "preqa",
    "pf"  : "aws",
    #if device has video stream capability
    "CameraOptions" : {
        "deviceport" : "/dev/video0",
        "video" : {
            "width" : "640",
            "height" : "480",
            "framerate" : "30/1"
        }
    }

}





"""
 * Type    : Callback Function "DeviceCallback()"
 * Usage   : Firmware will receive commands from cloud. You can manage your business logic as per received command.
 * Input   :  
 * Output  : Receive device command, firmware command and other device initialize error response 
"""

def DeviceCallback(msg):
    global Sdk
    fw_print("--- Command Message Received in Firmware ---")
    fw_print(json.dumps(msg))
    cmdType = None
    if msg != None and len(msg.items()) != 0:
        cmdType = msg["ct"] if "ct"in msg else None
    # Other Command
    if cmdType == 0:
        """
        * Type    : Public Method "sendAck()"
        * Usage   : Send device command received acknowledgment to cloud
        * 
        * - status Type
        *     st = 6; // Device command Ack status 
        *     st = 4; // Failed Ack
        * - Message Type
        *     msgType = 5; // for "0x01" device command 
        """
        data=msg
        if data != None:
            if "ack" in data and data["ack"]:
                if "id" in data:
                    Sdk.sendAckCmd(data["ack"],2,"sucessfull",data["id"])  #Executed (Cloud Only) = 0, 	Failed = 1, Executed Ack = 2
                else:
                    Sdk.sendAckCmd(data["ack"],2,"sucessfull") #Executed (Cloud Only) = 0, 	Failed = 1, Executed Ack = 2
    else:
        fw_print("rule command " + str(msg))

    # Firmware Upgrade
def DeviceFirmwareCallback(msg):
    global Sdk,device_list
    fw_print("--- firmware Command Message Received ---")
    fw_print(json.dumps(msg))
    cmdType = None
    if msg != None and len(msg.items()) != 0:
        cmdType = msg["ct"] if msg["ct"] != None else None

    if cmdType == 1:
        """
        * Type    : Public Method "sendAck()"
        * Usage   : Send firmware command received acknowledgement to cloud
        * - status Type
        *     st = 7; // firmware OTA command Ack status 
        *     st = 4; // Failed Ack
        * - Message Type
        *     msgType = 11; // for "0x02" Firmware command
        """
        data = msg
        if data != None:
            if ("urls" in data) and data["urls"]:
                for url_list in data["urls"]:
                    if "tg" in url_list:
                        for i in device_list:
                            if "tg" in i and (i["tg"] == url_list["tg"]):
                                Sdk.sendOTAAckCmd(data["ack"],5,"sucessfull",i["id"]) #Success=5, Executed (Cloud Only)=0, Failed = 1, Executed/DownloadingInProgress=2, Executed/DownloadDone=3, Failed/DownloadFailed=4
                    else:
                        Sdk.sendOTAAckCmd(data["ack"],5,"sucessfull") #Success=5, Executed (Cloud Only)=0, Failed = 1, Executed/DownloadingInProgress=2, Executed/DownloadDone=3, Failed/DownloadFailed=4

def DeviceConectionCallback(msg):
    cmdType = None
    if msg != None and len(msg.items()) != 0:
        cmdType = msg["ct"] if msg["ct"] != None else None
    #connection status
    if cmdType == 116:
        #Device connection status e.g. data["command"] = true(connected) or false(disconnected)
        fw_print(json.dumps(msg))

"""
 * Type    : Public Method "UpdateTwin()"
 * Usage   : Update the twin reported property
 * Input   : Desired property "key" and Desired property "value"
 * Output  : 
"""
# key = "<< Desired property key >>"; // Desired proeprty key received from Twin callback message
# value = "<< Desired Property value >>"; // Value of respective desired property
# Sdk.UpdateTwin(key,value)

"""
 * Type    : Callback Function "TwinUpdateCallback()"
 * Usage   : Manage twin properties as per business logic to update the twin reported property
 * Input   : 
 * Output  : Receive twin Desired and twin Reported properties
"""
def TwinUpdateCallback(msg):
    global Sdk
    if msg:
        fw_print("--- Twin Message Received ---")
        fw_print(json.dumps(msg))
        if ("desired" in msg) and ("reported" not in msg):
            for j in msg["desired"]:
                if ("version" not in j) and ("uniqueId" not in j):
                    Sdk.UpdateTwin(j,msg["desired"][j])

"""
 * Type    : Public data Method "SendData()"
 * Usage   : To publish the data on cloud D2C 
 * Input   : Predefined data object 
 * Output  : 
"""
def sendBackToSDK(sdk, dataArray):
    if(sdk.SendData(dataArray) == True):
        fw_print("Data Publish Success")
    else:
        fw_print("Data Publish Fail")
    time.sleep(interval)

def DirectMethodCallback(msg,methodname,rId):
    global Sdk,ACKdirect
    fw_print(str(msg))
    fw_print(str(methodname))
    fw_print(str(rId))
    # ACKdirect.append({"data":data,"status":200,"reqId":rId})
    Sdk.DirectMethodACK(msg,200,rId)

def DeviceChangCallback(msg):
    fw_print(msg)

def InitCallback(response):
    fw_print(response)

def delete_child_callback(msg):
    fw_print(msg)
    
def create_child_callback(msg):
    fw_print(msg)

def attributeDetails(data):
    fw_print("attribute received in firmware")
    fw_print(data)

def onReady(data):
    fw_print("Attribute got Sync ::")
    fw_print(str(data))
    global readyStatus
    readyStatus = True

"""
* Type    : Callback Function "OnCertSignedRequestCallback()"
* Usage   : Called by SDK when CSR-based certificate renewal is needed (ce=1 in sync response and rn received from Auth Challenge).
*           Firmware is responsible for generating a new CSR and signing it.
* Input   : rn (random number from auth challenge), device_id (device unique ID for CSR CN)
* Output  : Dict with "csr" (hex-encoded DER CSR), "sig" (hex-encoded signature), "fmt" (format string)
"""
def OnCertSignedRequestCallback(rn, device_id, company_id):
    """
    Generate a new CSR and signature for CSR-based certificate renewal.
    
    Based on the .NET reference implementation:
    1. Generate CSR using the EXISTING device private key (same key, new CSR)
    2. Sign data = (RN + CompanyID) bytes + CSR DER bytes using the device private key
    3. Return CSR hex and signature hex
    
    Args:
        rn: Random number string from Auth Challenge
        device_id: cpId-uniqueId to use as CSR Common Name
        company_id: Company GUID from discovery response
        
    Returns:
        dict: {"csr": "<hex-encoded DER CSR>", "sig": "<hex-encoded signature>", "fmt": "hex"}
        or None on failure
    """
    global SdkOptions
    fw_print(f"--- CSR Certificate Renewal Request ---")
    fw_print(f"Random Number (rn): {rn}")
    fw_print(f"Device ID for CSR CN: {device_id}")
    fw_print(f"Company ID: {company_id}")
    
    try:
        # Get current key path from SDK options
        key_path = SdkOptions.get("certificate", {}).get("SSLKeyPath", "")
        cert_path = SdkOptions.get("certificate", {}).get("SSLCertPath", "")
        
        if not key_path or not os.path.isfile(key_path):
            fw_error(f"Private key file not found: {key_path}")
            return None
        
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
        
        # Load the current device private key
        with open(key_path, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
        
        fw_print(f"Private key loaded from: {key_path}")
        
        # Read the current certificate to extract subject info
        subject_parts = [
            x509.NameAttribute(NameOID.COUNTRY_NAME, u"GB"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"London"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, u"London"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Global Security"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, u"IT Department"),
            x509.NameAttribute(NameOID.COMMON_NAME, device_id),
        ]
        
        # Try to read subject from existing cert (override CN with device_id)
        if os.path.isfile(cert_path):
            try:
                with open(cert_path, 'rb') as f:
                    cert_data = f.read()
                if b'-----BEGIN CERTIFICATE-----' in cert_data:
                    existing_cert = x509.load_pem_x509_certificate(cert_data, default_backend())
                else:
                    existing_cert = x509.load_der_x509_certificate(cert_data, default_backend())
                
                # Use existing subject but override CN with device_id
                subject_parts = []
                for attr in existing_cert.subject:
                    if attr.oid == NameOID.COMMON_NAME:
                        subject_parts.append(x509.NameAttribute(NameOID.COMMON_NAME, device_id))
                    else:
                        subject_parts.append(attr)
            except Exception as cert_ex:
                fw_print(f"Warning: Could not read existing cert subject: {cert_ex}, using defaults")
        
        # Step 1: Generate CSR using the SAME device private key
        fw_print("Step 1: Generating CSR with existing device private key...")
        csr_builder = x509.CertificateSigningRequestBuilder()
        csr_builder = csr_builder.subject_name(x509.Name(subject_parts))
        
        # Sign CSR with the EXISTING private key (same as .NET: GenerateCSR uses deviceCert's key)
        csr = csr_builder.sign(private_key, hashes.SHA256(), default_backend())
        
        # Get CSR in DER format
        csr_der = csr.public_bytes(serialization.Encoding.DER)
        csr_hex = csr_der.hex().upper()
        
        fw_print(f"CSR generated (CN={device_id}), DER bytes: {len(csr_der)}, hex length: {len(csr_hex)}")
        
        # Step 2: Generate signature
        # Data to sign = (RN + CompanyID) UTF-8 bytes + CSR DER bytes
        # This matches .NET: Combine(Encoding.UTF8.GetBytes(randomNumber + companyId), csrDerBytes)
        fw_print("Step 2: Generating signature...")
        rn_cid_bytes = (rn + company_id).encode('utf-8')
        data_to_sign = rn_cid_bytes + csr_der
        
        fw_print(f"Data to sign: (RN+CID) bytes: {len(rn_cid_bytes)}, CSR bytes: {len(csr_der)}, total: {len(data_to_sign)}")
        
        # Sign with device private key using PKCS1v15 + SHA256
        signature = private_key.sign(
            data_to_sign,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        sig_hex = signature.hex().upper()
        
        fw_print(f"Signature generated, hex length: {len(sig_hex)}")
        fw_print(f"--- CSR Certificate Renewal Request Complete ---")
        
        return {
            "csr": csr_hex,
            "sig": sig_hex,
            "fmt": "hex"
        }
            
    except Exception as ex:
        fw_error(f"CSR generation failed: {ex}")
        import traceback
        traceback.print_exc()
        return None


def _generate_csr_openssl(rn, device_id, key_path, cert_path):
    """
    Fallback: Generate CSR using OpenSSL command-line tool.
    Used when the 'cryptography' Python library is not available.
    """
    try:
        import tempfile
        
        # Generate new private key
        new_key_path = key_path + ".new"
        subprocess.run(
            ["openssl", "genrsa", "-out", new_key_path, "2048"],
            check=True, capture_output=True
        )
        
        # Generate CSR with CN = device_id
        csr_pem_path = tempfile.mktemp(suffix=".csr")
        subject = f"/C=GB/ST=London/L=London/O=Global Security/OU=IT Department/CN={device_id}"
        subprocess.run(
            ["openssl", "req", "-new", "-key", new_key_path, "-out", csr_pem_path, "-subj", subject],
            check=True, capture_output=True
        )
        
        # Convert CSR to DER and then to hex
        csr_der_path = tempfile.mktemp(suffix=".der")
        subprocess.run(
            ["openssl", "req", "-in", csr_pem_path, "-out", csr_der_path, "-outform", "DER"],
            check=True, capture_output=True
        )
        
        with open(csr_der_path, 'rb') as f:
            csr_der = f.read()
        csr_hex = csr_der.hex()
        
        # Sign the random number with current private key
        rn_file = tempfile.mktemp(suffix=".txt")
        sig_file = tempfile.mktemp(suffix=".sig")
        
        with open(rn_file, 'w') as f:
            f.write(rn)
        
        subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_path, "-out", sig_file, rn_file],
            check=True, capture_output=True
        )
        
        with open(sig_file, 'rb') as f:
            sig_bytes = f.read()
        sig_hex = sig_bytes.hex().upper()
        
        # Keep new key as .new file (SDK will rename after cert install)
        # new_key_path is already key_path + ".new" from openssl genrsa above
        
        # Cleanup temp files
        for tmp in [csr_pem_path, csr_der_path, rn_file, sig_file]:
            if os.path.exists(tmp):
                os.remove(tmp)
        
        fw_print(f"CSR generated via OpenSSL (CN={device_id})")
        fw_print(f"CSR hex length: {len(csr_hex)}")
        fw_print(f"Signature hex length: {len(sig_hex)}")
        
        return {
            "csr": csr_hex,
            "sig": sig_hex,
            "fmt": "hex"
        }
        
    except Exception as ex:
        fw_error(f"OpenSSL CSR generation failed: {ex}")
        # Cleanup
        if os.path.exists(key_path + ".new"):
            os.remove(key_path + ".new")
        return None

"""
* Type    : Test Function "testFileUpload()"
* Usage   : Test file upload functionality
* Input   : SDK instance
* Output  : Upload test results
"""
def testFileUpload(sdk):
    global file_upload_counter
    file_upload_counter += 1

    fw_print("========== File Upload Test ==========")

    # Test 1: Upload image from file path (if test image exists)
    test_image_path = "C:/Users/ankit.sangani/Downloads/55D215B0-5D4C-4AC3-ADA1-0E929FAC2631.jpg"
    if os.path.exists(test_image_path):
        fw_print("Test 1: UploadImage from file path")
        result = sdk.UploadImage(file_path=test_image_path)

        if result["success"]:
            fw_print("Upload Success!")
            fw_print("  S3 Key: " + result["s3_key"])
            fw_print("  Bucket: " + result["bucket"])
            fw_print("  URL: " + result["url"])
        else:
            fw_error("Upload Failed: " + result["error"])
    else:
        fw_print("Test 1 skipped: test_image.jpg not found")

    # Test 2: Upload with classification from file path
    if os.path.exists(test_image_path):
        fw_print("Test 2: UploadImageWithClassification from file path")
        result = sdk.UploadImageWithClassification(
            file_path=test_image_path,
            classification="test_classification",
            custom_attributes={
                "confidence": 0.95,
                "test_counter": file_upload_counter,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            }
        )

        if result["success"]:
            fw_print("Upload Success!")
            fw_print("  S3 Key: " + result["s3_key"])
            fw_print("  URL: " + result["url"])
            fw_print("  MQTT Published: " + str(result["mqtt_published"]))
        else:
            fw_error("Upload Failed: " + result["error"])
    else:
        fw_print("Test 2 skipped: test_image.jpg not found")

    fw_print("========== File Upload Test Complete ==========")
    print("")

"""
* Type    : Test Function "testGetCredentials()"
* Usage   : Test getting file upload credentials
* Input   : SDK instance
* Output  : Display credentials information
"""
def testGetCredentials(sdk):
    fw_print("========== Get File Upload Credentials Test ==========")

    # Get credentials using device certificate
    result = sdk.GetCredentials()

    if result["success"]:
        fw_print("Successfully obtained file upload credentials!")
        fw_print("")
        fw_print("Credentials Information:")
        fw_print("  Access Key ID: " + result["access_key_id"][:10] + "..." + result["access_key_id"][-4:])
        fw_print("  Secret Access Key: " + result["secret_access_key"][:10] + "..." + result["secret_access_key"][-4:])
        if result["session_token"]:
            fw_print("  Session Token: " + result["session_token"][:20] + "..." + result["session_token"][-10:])
        fw_print("  Expiration: " + result["expiration"])
        fw_print("")
        fw_print("Note: These are temporary credentials obtained via IoT Core credential provider")
        fw_print("      using your device certificate for authentication.")
    else:
        fw_error("Failed to get credentials: " + result["error"])

    fw_print("========== Get Credentials Test Complete ==========")
    print("")

"""
* Type    : Test Function "sendAudioDataWithArray()"
* Usage   : Send telemetry data with array (words) and nested objects in RPT format
* Input   : SDK instance
* Output  : Send audio transcript data with word array
"""
def sendAudioDataWithArray(sdk):
    fw_print("========== Send Audio Data with Array Test ==========")

    # Create audio data with nested object and array
    # Include "temperature" as a valid attribute so data goes to RPT
    # The audio data with array will be sent along with it
    tech_words = [
    "IoT", "AI", "MachineLearning", "DeepLearning", "NeuralNetwork", "API",
    "Lambda", "S3", "Kubernetes", "Docker", "Azure", "AWS", "GCP", "EdgeComputing",
    "Telemetry", "MQTT", "Blockchain", "Serverless", "Microservices", "BigData",
    "DevOps", "CI/CD", "NoSQL", "PostgreSQL", "GraphQL", "REST", "TensorFlow",
    "PyTorch", "CSharp", "NodeJS", "React", "FastAPI", "DataLake", "Analytics",
    "Encryption", "JWT", "Kafka", "Redis", "ElasticSearch", "Flask", "Terraform"
    ]

    audioData = {
    "dg": {
        "ppl": random.randint(1, 10),
        "fid": random.randint(1, 500)
    },
    "audio": {
        "transcript": "Full Text Of Speech Approx 1 OR 2 min",
        "words": [
            {
                "word": random.choice(tech_words),
                "weight": random.randint(1, 30)
            }
            for _ in range(random.randint(4, 8))  # generate 4 to 8 random words
        ]
    }
    }

    # Prepare data object for SDK
    dObj = [{
        "uniqueId": UniqueId,
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "data": audioData
    }]

    fw_print("Sending audio data with word array (RPT format)...")
    fw_print("Data structure:")
    fw_print(json.dumps(audioData, indent=2))

    # Send data
    if sdk.SendData(dObj):
        fw_print("Audio data with array sent successfully to RPT!")
        fw_print("Note: Data includes 'temperature' attribute for RPT routing")
    else:
        fw_print("Failed to send audio data")

    fw_print("========== Audio Data Array Test Complete ==========")
    print("")

def main():
    global SdkOptions,Sdk,ACKdirect,device_list,CameraOptions,test_file_upload,file_upload_counter,test_array_data
    
    try:
        """
        if SdkOptions["certificate"]:
            for prop in SdkOptions["certificate"]:
                if os.path.isfile(SdkOptions["certificate"][prop]):
                    pass
                else:
                    fw_print("please give proper path")
                    break
        else:
            fw_print("you are not use auth type CA sign or self CA sign ") 
        """    
        """
        * Type    : Object Initialization "IoTConnectSDK()"
        * Usage   : To Initialize SDK and Device cinnection
        * Input   : cpId, uniqueId, sdkOptions, env as explained above and DeviceCallback and TwinUpdateCallback is callback functions
        * Output  : Callback methods for device command and twin properties
        """

        with IoTConnectSDK(UniqueId,SdkOptions,DeviceConectionCallback) as Sdk:
            try:
                """
                * Type    : Public Method "GetAllTwins()"
                * Usage   : Send request to get all the twin properties Desired and Reported
                * Input   : 
                * Output  : 
                """
                    
                device_list=Sdk.Getdevice()
                Sdk.onDeviceCommand(DeviceCallback)
                Sdk.onTwinChangeCommand(TwinUpdateCallback)
                Sdk.onOTACommand(DeviceFirmwareCallback)
                Sdk.onDeviceChangeCommand(DeviceChangCallback)
                Sdk.onCertSignedRequest(OnCertSignedRequestCallback)
                Sdk.getTwins()
                Sdk.onReady(onReady)

                for method in directmethodlist:
                    Sdk.regiter_directmethod_callback(method,DirectMethodCallback)

                device_list=Sdk.Getdevice()
                #Sdk.delete_child("childid",delete_child_callback)
                #Sdk.createChildDevice("childid", "childtag", "childid", create_child_callback)
                #Sdk.UpdateTwin("ss01","mmm")
                #sdk.GetAllTwins()
                # Sdk.GetAttributes(attributeDetails)



                # ======= NEW: optional local test to start KVS WebRTC MASTER from this firmware process =======
                # To run: set environment variable KVS_TEST_CHANNEL_ARN to your channel ARN and AWS_CREDENTIAL_ENDPOINT to IoT credential endpoint.
                # Example (Linux/macOS):
                #   export KVS_TEST_CHANNEL_ARN="arn:aws:kinesisvideo:us-east-1:123456789012:channel/your-channel/..."
                #   export AWS_CREDENTIAL_ENDPOINT="https://.../credentials"
                # Then run this script. The device will call start_kvs_webrtc_from_devicecert in a thread.
                kvs_test_channel = os.getenv("KVS_TEST_CHANNEL_ARN")
                aws_credential_endpoint_env = os.getenv("AWS_CREDENTIAL_ENDPOINT")  # optional; if not provided, pass empty and function may fail
                kvs_test_region = os.getenv("AWS_REGION", "us-east-1")

                if kvs_test_channel:
                    fw_print(f"KVS test channel detected in env; starting KVS WebRTC MASTER on {kvs_test_channel}")
                    # certificate paths used by this process (from SdkOptions). Use Sdk._property for runtime values.
                    ca_path = None
                    cert_path = None
                    key_path = None
                    try:
                        # prefer runtime Sdk property if available
                        if hasattr(Sdk, "_property") and Sdk._property and "certificate" in Sdk._property:
                            certs = Sdk._property["certificate"]
                        else:
                            certs = SdkOptions.get("certificate", {})
                        ca_path = certs.get("SSLCaPath")
                        cert_path = certs.get("SSLCertPath")
                        key_path = certs.get("SSLKeyPath")
                    except Exception as e:
                        fw_error(f"Failed to resolve certificate paths: {e}")

                    # start in background thread so main loop continues
                    threading.Thread(
                        target=start_kvs_webrtc_from_devicecert,
                        args=(
                            kvs_test_channel,
                            UniqueId,
                            ca_path,
                            cert_path,
                            key_path,
                            aws_credential_endpoint_env,
                            SdkOptions.get("CameraOptions", {}),
                            kvs_test_region
                        ),
                        daemon=True
                    ).start()
                # ======= END NEW CODE =======

                # File Upload Test: Run once at startup if enabled
                if test_file_upload == True:
                    fw_print("Running file upload integration test...")
                    time.sleep(2)  # Wait a bit for full initialization

                    # Test getting credentials using device certificate
                    testGetCredentials(Sdk)

                    # Test file upload
                    testFileUpload(Sdk)
                    fw_print("File upload test completed. Continuing with telemetry...")
                    print("")

                # Array Data Test: Run once at startup if enabled
                if test_array_data == True:
                    fw_print("Running array data integration test...")
                    time.sleep(1)
                    sendAudioDataWithArray(Sdk)
                    fw_print("Array data test completed. Continuing with telemetry...")
                    print("")

                loop_counter = 0
                while True:
                    loop_counter += 1
                    #Sdk.GetAttributes()
                    """
                    * Add your device attributes and respective value here as per standard format defined in sdk documentation
                    * "time" : Date format should be as defined //"2021-01-24T10:06:17.857Z"
                    * "data" : JSON data type format // {"temperature": 15.55, "gyroscope" : { 'x' : -1.2 }}
                    """
                    dObj = [{
                        "uniqueId": UniqueId,
                        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        "data": {
                            "temperature": random.uniform(20.0, 35.0),
                            "humidity": random.uniform(40.0, 80.0)
                        }
                    }]
                    sendBackToSDK(Sdk, dObj)
                    time.sleep(interval)

                '''
                Client Disconnect Method
                '''
                Sdk.Dispose()

                time.sleep(10)
                    
            except KeyboardInterrupt:
                print ("Keyboard Interrupt Exception")
                # os.execl(sys.executable, sys.executable, *sys.argv)
                # os.abort()
                sys.exit(0)
                
                
    except Exception as ex:
        print(ex)
        # sys.exit(0)

if __name__ == "__main__":
    main()
