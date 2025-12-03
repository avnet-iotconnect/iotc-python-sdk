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


"""
* ## Prerequisite parameter to run this sampel code
* cpId         :: It need to get from the IoTConnect platform "Settings->Key Vault". 
* uniqueId     :: Its device ID which register on IotConnect platform and also its status has Active and Acquired
* env          :: It need to get from the IoTConnect platform "Settings->Key Vault". 
* interval     :: send data frequency in seconds
* sdkOptions   :: It helps to define the path of self signed and CA signed certificate as well as define the offlinne storage configuration.
"""


UniqueId = "Enter your Unique ID" 

Sdk=None
interval = 10
# add Direct Method
directmethodlist={}
ACKdirect=[]
device_list=[]
readyStatus = False

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
         # Certs
        "SSLKeyPath"  : "Enter device KEY certificate",    #aws=pk_devicename.pem   ||   #az=device.key
        "SSLCertPath" : "Enter device Certificate",    #aws=cert_devicename.crt ||   #az=device.pem
        "SSLCaPath"   : "Enter AWS/AZ Cloud certificate"     #aws=root-CA.pem         ||   #az=rootCA.pem
	},
    "offlineStorage":{
        "disabled": False,
	    "availSpaceInMb": 0.01,
	    "fileCount": 5,
        "keepalive":60
    },
    "skipValidation":False,
    # "devicePrimaryKey":"Enter Device Primary Key",
	# As per your Environment(Azure or Azure EU or AWS) uncomment single URL and commnet("#") rest of URLs.
    "discoveryUrl":"http://discovery.iotconnect.io",
    "IsDebug": True,
    "cpid" : "Enter CPID",
    "sId" : "",
    "env" : "Enter ENV",
    "pf"  : "Enter PF" # az / aws

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

def onCertReceivedCallback(cert_data):
    """
    Certificate Rotation Callback

    This callback is triggered when new certificates are received from IoTConnect
    during certificate rotation.

    Args:
        cert_data: Dictionary containing:
            - dc: Device certificate in DER Hex format
            - pk: Private key in DER Hex format
            - ackId: Acknowledgment ID
    """
    global Sdk, SdkOptions

    print("\n" + "="*60)
    print("Firmware :: Certificate Rotation - New certificates received")
    print("="*60)

    try:
        # Import utility for certificate conversion
        from iotconnect.common.util import util

        dc_hex = cert_data["dc"]
        pk_hex = cert_data["pk"]
        ack_id = cert_data["ackId"]

        print("Firmware :: Certificate data received")
        print("Firmware :: - Device Certificate Length: {} chars".format(len(dc_hex)))
        print("Firmware :: - Private Key Length: {} chars".format(len(pk_hex)))
        print("Firmware :: - ACK ID: {}".format(ack_id))

        # Define new certificate paths (backup old ones with timestamp)
        import time
        timestamp = int(time.time())

        old_cert_path = SdkOptions["certificate"]["SSLCertPath"]
        old_key_path = SdkOptions["certificate"]["SSLKeyPath"]

        # Backup old certificates
        backup_cert_path = old_cert_path + ".backup." + str(timestamp)
        backup_key_path = old_key_path + ".backup." + str(timestamp)

        print("\nFirmware :: Backing up old certificates...")
        try:
            import shutil
            if os.path.isfile(old_cert_path):
                shutil.copy2(old_cert_path, backup_cert_path)
                print("Firmware :: - Old certificate backed up to: {}".format(backup_cert_path))
            if os.path.isfile(old_key_path):
                shutil.copy2(old_key_path, backup_key_path)
                print("Firmware :: - Old key backed up to: {}".format(backup_key_path))
        except Exception as backup_ex:
            print("Firmware :: WARNING - Failed to backup old certificates: {}".format(str(backup_ex)))

        # Convert DER hex to PEM and save
        print("\nFirmware :: Converting certificates from DER hex to PEM format...")

        cert_pem = util.der_hex_to_pem(dc_hex, "CERTIFICATE")
        key_pem = util.der_hex_to_pem(pk_hex, "PRIVATE KEY")

        if not cert_pem or not key_pem:
            raise Exception("Failed to convert certificates to PEM format")

        print("Firmware :: - Certificates converted successfully")

        # Save new certificates
        print("\nFirmware :: Saving new certificates...")

        if not util.save_pem_file(cert_pem, old_cert_path):
            raise Exception("Failed to save certificate file")
        print("Firmware :: - Certificate saved to: {}".format(old_cert_path))

        if not util.save_pem_file(key_pem, old_key_path):
            raise Exception("Failed to save key file")
        print("Firmware :: - Private key saved to: {}".format(old_key_path))

        # Disconnect from current MQTT connection and reconnect with new certificates
        print("\nFirmware :: Disconnecting from MQTT broker...")
        print("Firmware :: This will temporarily interrupt the connection")

        # Call SDK method to disconnect and reconnect with new certificates
        print("\nFirmware :: Reconnecting with new certificates...")
        print("Firmware :: - Certificate: {}".format(old_cert_path))
        print("Firmware :: - Private Key: {}".format(old_key_path))

        connectivity_ok = Sdk.reconnect_with_new_certificates(old_cert_path, old_key_path, timeout=30)

        if connectivity_ok:
            print("\nFirmware :: ✓ Reconnection successful!")
            print("Firmware :: ✓ Device is now using new certificates")
            print("Firmware :: ✓ Device connectivity verified successfully")

            # Send ACK to IoTConnect
            print("\nFirmware :: Sending certificate installation ACK...")
            if Sdk.certReceiveAck(ack_id, True, "Certificate installed and verified successfully"):
                print("Firmware :: - ACK sent successfully")
                print("\n" + "="*60)
                print("Firmware :: Certificate Rotation Completed Successfully")
                print("="*60 + "\n")

                # Clean up old backup certificates (optional)
                print("Firmware :: Cleaning up backup certificates...")
                try:
                    if os.path.isfile(backup_cert_path):
                        os.remove(backup_cert_path)
                    if os.path.isfile(backup_key_path):
                        os.remove(backup_key_path)
                    print("Firmware :: - Backup certificates removed")
                except:
                    print("Firmware :: - Could not remove backup certificates (keeping for safety)")
            else:
                print("Firmware :: ERROR - Failed to send ACK")
        else:
            print("\nFirmware :: ✗ Reconnection failed!")
            print("Firmware :: ERROR - Device connectivity check failed")

            # Restore old certificates
            print("\nFirmware :: Rolling back to old certificates...")
            try:
                import shutil
                if os.path.isfile(backup_cert_path):
                    shutil.copy2(backup_cert_path, old_cert_path)
                    print("Firmware :: - Old certificate restored")
                if os.path.isfile(backup_key_path):
                    shutil.copy2(backup_key_path, old_key_path)
                    print("Firmware :: - Old key restored")

                # Try to reconnect with old certificates
                print("\nFirmware :: Attempting to reconnect with old certificates...")
                if Sdk.reconnect_with_new_certificates(old_cert_path, old_key_path, timeout=30):
                    print("Firmware :: - Successfully restored connection with old certificates")
                else:
                    print("Firmware :: - Failed to restore connection (device may require manual intervention)")
            except Exception as restore_ex:
                print("Firmware :: - Failed to restore old certificates: {}".format(str(restore_ex)))

            # Send failure ACK
            try:
                Sdk.certReceiveAck(ack_id, False, "Certificate installation failed - reconnection failed")
            except:
                print("Firmware :: - Could not send failure ACK")

    except Exception as ex:
        print("\nFirmware :: ERROR - Certificate rotation failed: {}".format(str(ex)))
        print("="*60 + "\n")

        # Send failure ACK
        try:
            Sdk.certReceiveAck(ack_id, False, "Certificate installation failed: " + str(ex))
        except:
            pass


def main():
    global SdkOptions,Sdk,ACKdirect,device_list
    
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
                Sdk.onCertReceived(onCertReceivedCallback)
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



                while True:
                    #Sdk.GetAttributes()
                    """
                    * Add your device attributes and respective value here as per standard format defined in sdk documentation
                    * "time" : Date format should be as defined //"2021-01-24T10:06:17.857Z"
                    * "data" : JSON data type format // {"temperature": 15.55, "gyroscope" : { 'x' : -1.2 }}
                    """

                    data = {
                        "long1":random.randint(6000, 9000),
                        "integer1": random.randint(100, 200),
                        "decimal1":random.uniform(10.5, 75.5),
                        "date1":datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "time1":"11:55:22",
                        "bit1":1,
                        "string1":"red",
                        "datetime1":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        "gyroscope": {
                            'bit1':0,
                            'boolean1': True,
                            'date1': datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                            "datetime1": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                            "decimal1":random.uniform(10.5, 75.5),
                            "integer1":random.randint(60, 600),
                            "latlong1":[random.uniform(10.5, 75.5),random.uniform(10.5, 75.5)],
                            "long1":random.randint(60, 600000),
                            "string1":"green",
                            "time1":"11:44:22",
                            "temperature":random.randint(50, 90)
                            }
                    }

                    dObj = [{
                    # "uniqueId": UniqueId,
                    "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "data": data
                    }]

                    

                    # """
                    # * Gateway device input data format Example:
                    # """
                    
                    
                    # dObj = [ {
                    #              "uniqueId":"UniqueId",
                    #              "time":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    #              "data": {
                    #                      "temperature":random.randint(30, 50)
                    #                      }
                    #              },
                    #              {
                    #                 "uniqueId":"childUniqueId",
                    #                 "time":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    #                 "data": {
                    #                      "temperature":random.randint(30, 50)
                    #                      }
                    #                },
                    #              {
                    #                 "uniqueId":"childUniqueId",
                    #                 "time":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    #                 "data": {
                    #                      "temperature":random.randint(30, 50)
                    #                      }
                    #                }
                    #             ]

                    #dataArray.append(dObj)
                    #print (dObj)      
                    if(readyStatus == True):
                        print("Firmware :: readyStatus == True")
                        sendBackToSDK(Sdk, dObj)
                    else:
                        print("Firmware :: readyStatus == False")

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
