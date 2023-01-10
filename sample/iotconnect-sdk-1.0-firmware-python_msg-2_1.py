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


UniqueId = "<<Your Device UniqueID>>" 
SId = "<<Your Company SID>>"

Sdk=None
interval = 30
directmethodlist={}
ACKdirect=[]
device_list=[]
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
		"SSLKeyPath"  : "",    #aws=pk_devicename.pem   ||   #az=device.key
		"SSLCertPath" : "",    #aws=cert_devicename.crt ||   #az=device.pem
		"SSLCaPath"   : ""     #aws=root-CA.pem         ||   #az=rootCA.pem 
        
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
    # "discoveryUrl":"https://discovery.iotconnect.io", #Azure All Environment 
    "discoveryUrl":"http://52.204.155.38:219", #AWS pre-QA Environment
    "IsDebug": False
   
}


"""
 * Type    : Callback Function "DeviceCallback()"
 * Usage   : Firmware will receive commands from cloud. You can manage your business logic as per received command.
 * Input   :  
 * Output  : Receive device command, firmware command and other device initialize error response 
"""

def DeviceCallback(msg):
    global Sdk
    print("\n--- Command Message Received in Firmware ---")
    print(json.dumps(msg))
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
        print("rule command",msg)

    # Firmware Upgrade
def DeviceFirmwareCallback(msg):
    global Sdk,device_list
    print("\n--- firmware Command Message Received ---")
    print(json.dumps(msg))
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
        print(json.dumps(msg))

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
        print("--- Twin Message Received ---")
        print(json.dumps(msg))
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
    sdk.SendData(dataArray)
    time.sleep(interval)

def DirectMethodCallback1(msg,methodname,rId):
    global Sdk,ACKdirect
    print(msg)
    print(methodname)
    print(rId)
    data={"data":"succed"}
    #return data,200,rId
    ACKdirect.append({"data":data,"status":200,"reqId":rId})
    #Sdk.DirectMethodACK(data,200,rId)

def DirectMethodCallback(msg,methodname,rId):
    global Sdk,ACKdirect
    print(msg)
    print(methodname)
    print(rId)
    data={"data":"fail"}
    #return data,200,rId
    ACKdirect.append({"data":data,"status":200,"reqId":rId})
    #Sdk.DirectMethodACK(data,200,rId)

def DeviceChangCallback(msg):
    print(msg)

def InitCallback(response):
    print(response)

def delete_child_callback(msg):
    print(msg)

def attributeDetails(data):
    print ("attribute received in firmware")
    print (data)
    



def main():
    global SId,SdkOptions,Sdk,ACKdirect,device_list
    
    try:
        """
        if SdkOptions["certificate"]:
            for prop in SdkOptions["certificate"]:
                if os.path.isfile(SdkOptions["certificate"][prop]):
                    pass
                else:
                    print("please give proper path")
                    break
        else:
            print("you are not use auth type CA sign or self CA sign ") 
        """    
        """
        * Type    : Object Initialization "IoTConnectSDK()"
        * Usage   : To Initialize SDK and Device cinnection
        * Input   : cpId, uniqueId, sdkOptions, env as explained above and DeviceCallback and TwinUpdateCallback is callback functions
        * Output  : Callback methods for device command and twin properties
        """
        with IoTConnectSDK(UniqueId,SId,SdkOptions,DeviceConectionCallback) as Sdk:
            try:
                """
                * Type    : Public Method "GetAllTwins()"
                * Usage   : Send request to get all the twin properties Desired and Reported
                * Input   : 
                * Output  : 
                """
                Sdk.onDeviceCommand(DeviceCallback)
                Sdk.onTwinChangeCommand(TwinUpdateCallback)
                Sdk.onOTACommand(DeviceFirmwareCallback)
                Sdk.onDeviceChangeCommand(DeviceChangCallback)
                Sdk.getTwins()
                device_list=Sdk.Getdevice()
                #Sdk.delete_chield("childid",delete_child_callback)

                #Sdk.UpdateTwin("ss01","mmm")
                #sdk.GetAllTwins()
                # Sdk.GetAttributes(attributeDetails)
                while True:
                    #Sdk.GetAttributes()
                    """
                    * Non Gateway device input data format Example:
					
                    """

                    
                    data = {
                    "temperature":random.randint(30, 50),
                    "long1":random.randint(6000, 9000),
                    "integer1": random.randint(100, 200),
                    "decimal1":random.uniform(10.5, 75.5),
                    "date1":datetime.utcnow().strftime("%Y-%m-%d"),
                    "time1":"11:55:22",
                    "bit1":1,
                    "string1":"red",
                    "datetime1":datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "gyro": {
                        'bit1':0,
                        'boolean1': True,
                        'date1': datetime.utcnow().strftime("%Y-%m-%d"),
                        "datetime1": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
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
                        "uniqueId": UniqueId,
                        "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        "data": data
                    }]
                    

                    """
                    * Gateway device input data format Example:
                    """
                    
                    
                    # dObj = [{
                    #             "uniqueId":UniqueId,
                    #             "time":datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    #             "data": {
                    #                     "temperature":-2147483649,
                    #                     "decimal1":8121.2,
                    #                     "long1":9007199254740991,
                    #                     "gyro": {
                    #                         'bit1':0,
                    #                         'boolean1': True,
                    #                         'date1': datetime.utcnow().strftime("%Y-%m-%d"),
                    #                         "datetime1": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    #                         "decimal1":2.555,
                    #                         "integer1":884,
                    #                         "latlong1":78945,
                    #                         "long1":999,
                    #                         "string1":"green",
                    #                         "time1":"11:44:22",
                    #                         "temperature":22
                    #                         }
                    #                     }
                    #             },
                    #             {
                    #             "uniqueId":UniqueId+"c",
                    #             "time":datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    #             "data": {
                    #                     "temperature":2323,
                    #                     "decimal1":2.555,
                    #                     "long1":36544,
                    #                     "gyro": {
                    #                         'bit1':0,
                    #                         'boolean1': True,
                    #                         'date1': datetime.utcnow().strftime("%Y-%m-%d"),
                    #                         "datetime1": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    #                         "decimal1":2.555,
                    #                         "integer1":884,
                    #                         "latlong1":78945,
                    #                         "long1":999,
                    #                         "string1":"green",
                    #                         "time1":"11:44:22",
                    #                         "temperature":10
                    #                         }
                    #                     }
                    #             }
                                # {
                                # "uniqueId":UniqueId+"c1",
                                # "time":datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                                # "data": {
                                #         "Temperature":"hi",
                                #         "gyro": {
                                #             'bit1':0,
                                #             'boolean1': True,
                                #             'date1': datetime.utcnow().strftime("%Y-%m-%d"),
                                #             "datetime1": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                                #             "decimal1":2.555,
                                #             "integer1":884,
                                #             "latlong1":78945,
                                #             "long1":999,
                                #             "string1":"green",
                                #             "time1":"11:44:22",
                                #             "temperature":10
                                #             }
                                #         }
                                # }
                            # ]
                                

                    
                    """
                    * Add your device attributes and respective value here as per standard format defined in sdk documentation
                    * "time" : Date format should be as defined //"2021-01-24T10:06:17.857Z" 
                    * "data" : JSON data type format // {"temperature": 15.55, "gyroscope" : { 'x' : -1.2 }}
                    """
                    #dataArray.append(dObj)
                    #print (dObj)      
                    sendBackToSDK(Sdk, dObj)
                    
            except KeyboardInterrupt:
                print ("Keyboard Interrupt Exception")
                # os.execl(sys.executable, sys.executable, *sys.argv)
                os.abort()
                # sys.exit(0)
                
                
    except Exception as ex:
        # print(ex.message)
        sys.exit(0)

if __name__ == "__main__":
    main()
