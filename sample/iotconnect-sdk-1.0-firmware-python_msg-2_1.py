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

# New import: helper to start KVS WebRTC MASTER on device (created earlier)
from iotconnect.client.awskinesisclient import start_kvs_webrtc_from_devicecert

"""
* ## Prerequisite parameter to run this sampel code
* cpId         :: It need to get from the IoTConnect platform "Settings->Key Vault". 
* uniqueId     :: Its device ID which register on IotConnect platform and also its status has Active and Acquired
* env          :: It need to get from the IoTConnect platform "Settings->Key Vault". 
* interval     :: send data frequency in seconds
* sdkOptions   :: It helps to define the path of self signed and CA signed certificate as well as define the offlinne storage configuration.
"""

UniqueId = "reInvent"

Sdk=None
interval = 10
# add Direct Method
directmethodlist={}
ACKdirect=[]
device_list=[]
readyStatus = False
file_upload_counter = 0
test_file_upload = True  # Set to True to enable file upload testing
test_array_data = True  # Set to True to enable array data testing

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
        "SSLKeyPath"  : "c:/Users/ankit.sangani/Downloads/reInvent-certificates (2)/pk_reInvent demo.pem",    #aws=pk_devicename.pem   ||   #az=device.key
        "SSLCertPath" : "c:/Users/ankit.sangani/Downloads/reInvent-certificates (2)/cert_reInvent demo.crt",    #aws=cert_devicename.crt ||   #az=device.pem
        "SSLCaPath"   : "c:/SW-AnkitSangani/AWS/sdk/AmazonrootCA.pem"     #aws=root-CA.pem         ||   #az=rootCA.pem
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
    "cpid" : "mssql",
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
    print("Firmware :: --- Command Message Received in Firmware ---")
    print("Firmware :: " + json.dumps(msg))
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
        print("Firmware :: rule command",msg)

    # Firmware Upgrade
def DeviceFirmwareCallback(msg):
    global Sdk,device_list
    print("Firmware :: --- firmware Command Message Received ---")
    print("Firmware :: " + json.dumps(msg))
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
        print("Firmware :: " + json.dumps(msg))

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
        print("Firmware :: --- Twin Message Received ---")
        print("Firmware :: " + json.dumps(msg))
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
        print("Firmware :: Data Publish Success")
    else:
        print("Firmware :: Data Publish Fail")
    time.sleep(interval)

def DirectMethodCallback(msg,methodname,rId):
    global Sdk,ACKdirect
    print("Firmware :: " + str(msg))
    print("Firmware :: " +  str(methodname))
    print("Firmware :: " +  str(rId))
    # ACKdirect.append({"data":data,"status":200,"reqId":rId})
    Sdk.DirectMethodACK(msg,200,rId)

def DeviceChangCallback(msg):
    print("Firmware :: " + msg)

def InitCallback(response):
    print("Firmware :: " + response)

def delete_child_callback(msg):
    print("Firmware :: " + msg)
    
def create_child_callback(msg):
    print("Firmware :: " + msg)

def attributeDetails(data):
    print("Firmware :: attribute received in firmware")
    print("Firmware :: " + data)

def onReady(data):
    print("Firmware :: Attribute got Sync ::")
    print("Firmware :: " + str(data))
    global readyStatus
    readyStatus = True

"""
* Type    : Test Function "testFileUpload()"
* Usage   : Test file upload functionality
* Input   : SDK instance
* Output  : Upload test results
"""
def testFileUpload(sdk):
    global file_upload_counter
    file_upload_counter += 1

    print("Firmware :: ========== File Upload Test ==========")

    # Test 1: Upload image from file path (if test image exists)
    test_image_path = "C:/Users/ankit.sangani/Downloads/55D215B0-5D4C-4AC3-ADA1-0E929FAC2631.jpg"
    if os.path.exists(test_image_path):
        print("Firmware :: Test 1: UploadImage from file path")
        result = sdk.UploadImage(file_path=test_image_path)

        if result["success"]:
            print("Firmware :: Upload Success!")
            print("Firmware ::   S3 Key: " + result["s3_key"])
            print("Firmware ::   Bucket: " + result["bucket"])
            print("Firmware ::   URL: " + result["url"])
        else:
            print("Firmware :: Upload Failed: " + result["error"])
    else:
        print("Firmware :: Test 1 skipped: test_image.jpg not found")

    # Test 2: Upload with classification from file path
    if os.path.exists(test_image_path):
        print("Firmware :: Test 2: UploadImageWithClassification from file path")
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
            print("Firmware :: Upload Success!")
            print("Firmware ::   S3 Key: " + result["s3_key"])
            print("Firmware ::   URL: " + result["url"])
            print("Firmware ::   MQTT Published: " + str(result["mqtt_published"]))
        else:
            print("Firmware :: Upload Failed: " + result["error"])
    else:
        print("Firmware :: Test 2 skipped: test_image.jpg not found")

    print("Firmware :: ========== File Upload Test Complete ==========")
    print("")

"""
* Type    : Test Function "testGetCredentials()"
* Usage   : Test getting file upload credentials
* Input   : SDK instance
* Output  : Display credentials information
"""
def testGetCredentials(sdk):
    print("Firmware :: ========== Get File Upload Credentials Test ==========")

    # Get credentials using device certificate
    result = sdk.GetCredentials()

    if result["success"]:
        print("Firmware :: Successfully obtained file upload credentials!")
        print("Firmware :: ")
        print("Firmware :: Credentials Information:")
        print("Firmware ::   Access Key ID: " + result["access_key_id"][:10] + "..." + result["access_key_id"][-4:])
        print("Firmware ::   Secret Access Key: " + result["secret_access_key"][:10] + "..." + result["secret_access_key"][-4:])
        if result["session_token"]:
            print("Firmware ::   Session Token: " + result["session_token"][:20] + "..." + result["session_token"][-10:])
        print("Firmware ::   Expiration: " + result["expiration"])
        print("Firmware :: ")
        print("Firmware :: Note: These are temporary credentials obtained via IoT Core credential provider")
        print("Firmware ::       using your device certificate for authentication.")
    else:
        print("Firmware :: Failed to get credentials: " + result["error"])

    print("Firmware :: ========== Get Credentials Test Complete ==========")
    print("")

"""
* Type    : Test Function "sendAudioDataWithArray()"
* Usage   : Send telemetry data with array (words) and nested objects in RPT format
* Input   : SDK instance
* Output  : Send audio transcript data with word array
"""
def sendAudioDataWithArray(sdk):
    print("Firmware :: ========== Send Audio Data with Array Test ==========")

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

    print("Firmware :: Sending audio data with word array (RPT format)...")
    print("Firmware :: Data structure:")
    print("Firmware :: ", json.dumps(audioData, indent=2))

    # Send data
    if sdk.SendData(dObj):
        print("Firmware :: Audio data with array sent successfully to RPT!")
        print("Firmware :: Note: Data includes 'temperature' attribute for RPT routing")
    else:
        print("Firmware :: Failed to send audio data")

    print("Firmware :: ========== Audio Data Array Test Complete ==========")
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
                    print("Firmware :: please give proper path")
                    break
        else:
            print("Firmware :: you are not use auth type CA sign or self CA sign ") 
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
                    print(f"Firmware :: KVS test channel detected in env; starting KVS WebRTC MASTER on {kvs_test_channel}")
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
                        print("Firmware :: Failed to resolve certificate paths:", e)

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
                    print("Firmware :: Running file upload integration test...")
                    time.sleep(2)  # Wait a bit for full initialization

                    # Test getting credentials using device certificate
                    testGetCredentials(Sdk)

                    # Test file upload
                    testFileUpload(Sdk)
                    print("Firmware :: File upload test completed. Continuing with telemetry...")
                    print("")

                # Array Data Test: Run once at startup if enabled
                if test_array_data == True:
                    print("Firmware :: Running array data integration test...")
                    time.sleep(1)
                    sendAudioDataWithArray(Sdk)
                    print("Firmware :: Array data test completed. Continuing with telemetry...")
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
                    sendAudioDataWithArray(Sdk)
                    time.sleep(10)

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
