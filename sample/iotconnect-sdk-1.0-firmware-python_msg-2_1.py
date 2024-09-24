"""
  ******************************************************************************
  * @file   : iotconnect-sdk-1.0-firmware-python_msg-2_1.py
  * @author : Softweb Solutions An Avnet Company
  * @modify : 02-January-2023
  * @brief  : Firmware part for Python SDK 1.0
  ******************************************************************************
"""

"""
 * Hope you have installed the Python SDK v1.0 as guided in README.md file or from documentation portal. 
 * Import the IoTConnect SDK package and other required packages
"""

import sys
import json
import time
import threading
import random
from iotconnect import IoTConnectSDK
from datetime import datetime
import os

"""
* ## Prerequisite parameter to run this sampel code
* cpId         :: It need to get from the IoTConnect platform "Settings->Key Vault". 
* uniqueId     :: Its device ID which register on IotConnect platform and also its status has Active and Acquired
* env          :: It need to get from the IoTConnect platform "Settings->Key Vault". 
* interval     :: send data frequency in seconds
* sdkOptions   :: It helps to define the path of self signed and CA signed certificate as well as define the offlinne storage configuration.
"""

UniqueId = " " 

Sdk=None
interval = 30
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
        "SSLKeyPath"  : "  ",    #aws=pk_devicename.pem   ||   #az=device.key
        "SSLCertPath" : "  ",    #aws=cert_devicename.crt ||   #az=device.pem
        "SSLCaPath"   : "  "     #aws=root-CA.pem         ||   #az=rootCA.pem
 
        
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
    "discoveryUrl":"https://discovery.iotconnect.io",
    "IsDebug": False,
    "cpid" : "  ",
    "sId" : "  ",
    "env" : "  ",
    "pf"  : " " # az / aws
   
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
            #print(data)
            if "id" in data:
                if "ack" in data and data["ack"]:
                    Sdk.sendAckCmd(data["ack"],7,"sucessfull",data["id"])  #fail=4,executed= 5,sucess=7,6=executedack
            else:
                if "ack" in data and data["ack"]:
                    Sdk.sendAckCmd(data["ack"],7,"sucessfull") #fail=4,executed= 5,sucess=7,6=executedack
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
                                Sdk.sendOTAAckCmd(data["ack"],0,"sucessfull",i["id"]) #Success=0, Failed = 1, Executed/DownloadingInProgress=2, Executed/DownloadDone=3, Failed/DownloadFailed=4
                    else:
                        Sdk.sendOTAAckCmd(data["ack"],0,"sucessfull") #Success=0, Failed = 1, Executed/DownloadingInProgress=2, Executed/DownloadDone=3, Failed/DownloadFailed=4

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

def DirectMethodCallback1(msg,methodname,rId):
    global Sdk,ACKdirect
    print("Firmware :: " + msg)
    print("Firmware :: " + methodname)
    print("Firmware :: " + rId)
    data={"data":"succed"}
    #return data,200,rId
    ACKdirect.append({"data":data,"status":200,"reqId":rId})
    #Sdk.DirectMethodACK(data,200,rId)

def DirectMethodCallback(msg,methodname,rId):
    global Sdk,ACKdirect
    print("Firmware :: " + msg)
    print("Firmware :: " + methodname)
    print("Firmware :: " + rId)
    data={"data":"fail"}
    #return data,200,rId
    ACKdirect.append({"data":data,"status":200,"reqId":rId})
    #Sdk.DirectMethodACK(data,200,rId)

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
    global readyStatus
    readyStatus = True


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
                Sdk.getTwins()
                Sdk.onReady(onReady)
                device_list=Sdk.Getdevice()
                #Sdk.delete_child("childid",delete_child_callback)
                #Sdk.createChildDevice("childid", "childtag", "childid", create_child_callback)
                #Sdk.UpdateTwin("ss01","mmm")
                #sdk.GetAllTwins()
                # Sdk.GetAttributes(attributeDetails)

                for i in range(5):
                    #Sdk.GetAttributes()
                    """
                    * Add your device attributes and respective value here as per standard format defined in sdk documentation
                    * "time" : Date format should be as defined //"2021-01-24T10:06:17.857Z"
                    * "data" : JSON data type format // {"temperature": 15.55, "gyroscope" : { 'x' : -1.2 }}
                    """

                    data= {
                        "AString" : "AString",
                        "ADecimal" : random.uniform(10.5, 75.5),
                        "AObject" : {} ,
                        "AInteger" : random.randint(100, 200),
                        "ADate" : datetime.utcnow().strftime("%Y-%m-%d"),
                        "ABoolean" : False,
                        "ABit" : True,
                        "ADateTime" : datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        "ATime" : "11:55:22",
                        "ALatLong" : [random.uniform(10.5, 75.5),random.uniform(10.5, 75.5)],
                        "ALong" : random.randint(60, 600000)
                    }

                    dObj = [{
                    "uniqueId": UniqueId,
                    "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "data": data
                    }]

                    #dataArray.append(dObj)
                    #print (dObj)      
                    if(readyStatus == True):
                        print("Firmware :: readyStatus == True")
                        sendBackToSDK(Sdk, dObj)
                    else:
                        print("Firmware :: readyStatus == False")

                    time.sleep(60)

                '''
                Client Disconnect Method
                '''
                Sdk.Dispose()

                time.sleep(10)
                    
            except KeyboardInterrupt:
                print ("Keyboard Interrupt Exception")
                # os.execl(sys.executable, sys.executable, *sys.argv)
                # os.abort()
                # sys.exit(0)
                
                
    except Exception as ex:
        print(ex)
        # sys.exit(0)

if __name__ == "__main__":
    main()
