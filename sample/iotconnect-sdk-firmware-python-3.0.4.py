"""
  ******************************************************************************
  * @file   : iotconnect-sdk-firmware-python-3.0.4.py 
  * @author : Softweb Solutions An Avnet Company
  * @modify : 2-September-2022
  * @brief  : Firmware part for Python SDK 3.0.4
  ******************************************************************************
"""

"""
 * Hope you have installed the Python SDK v3.0.4 as guided in README.md file or from documentation portal. 
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

flag = False
if sys.version_info >= (3, 5):
    flag=True


"""
* ## Prerequisite parameter to run this sampel code
* cpId         :: It need to get from the IoTConnect platform "Settings->Key Vault". 
* uniqueId     :: Its device ID which register on IotConnect platform and also its status has Active and Acquired
* env          :: It need to get from the IoTConnect platform "Settings->Key Vault". 
* interval     :: send data frequency in seconds
* sdkOptions   :: It helps to define the path of self signed and CA signed certificate as well as define the offlinne storage configuration.
"""

Env= "<<Environmner>>"
UniqueId = "<<Device ID>>"
CpId= "<<CPID>>"
Sdk = None
interval = 60
dataArray = []
device_cmd=[]
"""
* sdkOptions is optional. Mandatory for "certificate" X.509 device authentication type
* "certificate" : It indicated to define the path of the certificate file. Mandatory for X.509/SSL device CA signed or self-signed authentication type only.
* 	- SSLKeyPath: your device key
* 	- SSLCertPath: your device certificate
* 	- SSLCaPath : Root CA certificate
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
		"SSLKeyPath" : "<<path>>/device.key",  
		"SSLCertPath" : "<<path>>/device.pem",
		"SSLCaPath" : "<<path>>/ms.pem"
	},
    "offlineStorage":{
        "disabled": False,
	    "availSpaceInMb": 0.01,
	    "fileCount": 5
    }
}

"""
 * Type    : Callback Function "DeviceCallback()"
 * Usage   : Firmware will receive commands from cloud. You can manage your business logic as per received command.
 * Input   :  
 * Output  : Receive device command, firmware command and other device initialize error response 
"""
"""
NOTE:- Try to avoid sendACK from callback. please store in to a variable and after that send it.
"""
def DeviceCallback(msg):
    global device_cmd
    print("\n--- Command Message Received ---")
    #print(json.dumps(msg))
    cmdType = None
    if msg != None and len(msg.items()) != 0:
        cmdType = msg["cmdType"] if msg["cmdType"] != None else None
    # Other Command
    if cmdType == "0x01":
        print(json.dumps(msg))
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
            d2cMsg={
                "ackId" : data["ackId"],
                "st" : 6,
                "msg" : "",
                "childId" : ""
            }
            device_cmd.append([d2cMsg,5]) # 5 : command acknowledgement
    # Firmware Upgrade
    elif cmdType == "0x02":
        print(json.dumps(msg))
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
            if "uniqueId" in data['urls'][0]:
                d2cMsg={
                    "ackId" : data["ackId"],
                    "st" : 7,
                    "msg" : "OTA updated successfully..!!",
                    "childId" : data['urls'][0]['uniqueId']
                }
                device_cmd.append([d2cMsg,11]) # 11 : Firmware acknowledgement
            else:
                d2cMsg={
                    "ackId" : data["ackId"],
                    "st" : 7,
                    "msg" : "OTA updated successfully..!!",
                    "childId" : ''
                }
                device_cmd.append([d2cMsg,11]) # 11 : Firmware acknowledgement
    #connection status
    elif cmdType == "0x16":
        #Device connection status e.g. data["command"] = true(connected) or false(disconnected)
        print(json.dumps(msg))
    else:
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
"""
 * Type    : Public data Method "DirectMethodACK()"
 * Usage   : To send the Acknowledgement of Direct Method 
 * Input   : Data(format should be in JSON), Status, Request ID(rID) 
 * Output  : 
"""
def DirectMethodCallback(msg,rId):
    global Sdk
    print(msg)
    #print(methodname)
    print(rId)
    data={"data":"fail"}
    Sdk.DirectMethodACK(data,200,rId)#Status should be 200

def main():
    global dataArray,CpId,UniqueId,Env,SdkOptions,Sdk,flag,device_cmd
    try:
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
        * Type    : Object Initialization "IoTConnectSDK()"
        * Usage   : To Initialize SDK and Device cinnection
        * Input   : cpId, uniqueId, sdkOptions, env as explained above and DeviceCallback and TwinUpdateCallback is callback functions
        * Output  : Callback methods for device command and twin properties
        """
        with IoTConnectSDK(CpId, UniqueId, DeviceCallback, TwinUpdateCallback,SdkOptions,Env) as Sdk:
            try:
                """
                * Type    : Public Method "GetAllTwins()"
                * Usage   : Send request to get all the twin properties Desired and Reported
                * Input   : 
                * Output  : 
                """
                """
                * Type    : Public Method "regiter_directmethod_callback()"
                * Usage   : Register your direct method in SDK 
                * Input   : Method name and Method callback 
                * Output  : 
                """
				#Note: If you want to get the response of direct method from the cloud then you have to register your method name.
                
                val = 'y'
                while(val == 'y'):
                    if flag:
                        val=input("Do you want to regiter direct method(Y/N): ").rstrip()
                        if val.lower() == 'y':
                            methodname=input("please Enter your method Name : ").rstrip()
                            if methodname:
                                Sdk.regiter_directmethod_callback(methodname,DirectMethodCallback)
                    else:
                        val=raw_input("Do you want to regiter direct method(Y/N): ").rstrip()
                        if val.lower() == 'y':
                            methodname=raw_input("please Enter your method Name : ").rstrip()
                            if methodname:
                                Sdk.regiter_directmethod_callback(methodname,DirectMethodCallback)
                #sdk.GetAllTwins()
                
                while True:
                    dataArray=[]
                    
                    """
                    * Non Gateway device input data format Example:
					
                    """

                    
                    data = {
					"Temperature": random.randint(0,1),
                    "String1": "hello",
                    "humidity":random.randint(0,10),
                    "light":random.randint(10,20),
                    "motion":random.randint(20,30),
                    "magneto":{
                        "x":random.randint(0,1),
                        "y":random.randint(0,1),
                        "z":"my_data"
                    },
                    "Gyroscope": {
                    'num1': random.randint(0,1),
                    'str1': "test"                  
                    }
					} 
                    dObj = [{
                        "uniqueId": UniqueId,
                        "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        "data": data
                    }]
					

                    # Gateway device input data format Example:
                    
                    """
                    dObj = [{
                    "uniqueId":UniqueId,
                    "time":datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "data":
                    {
                    #"temperature": random.randint(1,100),
                    "temperature": -0.13366056978702545,
                    "humidity": "p.string",
                    "gyro": {
                    'n': random.randint(1,100),
                    's': "p.string"                    
                    }
                    }
                    },{
                    "uniqueId":"parasc",
                    "time":datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "data":
                    {
                    "temperature": random.randint(1,100),
                    "humidity": "c.string",
                    "gyro": {
                    'n': random.randint(1,100),
                    's': "c.string"
                    }
                    }
                    }]
                    """

					
                    """
                    * Add your device attributes and respective value here as per standard format defined in sdk documentation
                    * "time" : Date format should be as defined //"2021-01-24T10:06:17.857Z" 
                    * "data" : JSON data type format // {"temperature": 15.55, "gyroscope" : { 'x' : -1.2 }}
                    """
                    #dataArray.append(dObj)     
                    sendBackToSDK(Sdk,dObj)
                    if device_cmd:
                        for i in device_cmd:
                            Sdk.SendACK(i[0],i[1])
                        device_cmd=[]
            except KeyboardInterrupt:
                sys.exit(0)
    except Exception as ex:
        print(ex.message)
        sys.exit(0)

if __name__ == "__main__":
    main()
