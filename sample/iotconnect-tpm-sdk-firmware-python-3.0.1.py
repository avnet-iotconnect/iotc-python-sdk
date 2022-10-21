"""
  ******************************************************************************
  * @file   : iotconnect-tpm-sdk-firmware-python-3.0.1.py
  * @author : Softweb Solutions An Avnet Company
  * @modify : 14-Apr-2021
  * @brief  : Firmware part for Python SDK 3.0.1
  ******************************************************************************
"""

"""
 * Hope you have installed the Python SDK v3.0.1 as guided in README.md file or from documentation portal. 
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
 * cpId              :: It need to get from the IoTConnect platform "Settings->Key Vault". 
 * uniqueId          :: Its device ID which register on IotConnect platform and also its status has Active and Acquired
 * scopeId           :: It need to get from the IoTConnect platform "Settings->Key Vault->DPS Info".
 * env               :: It need to get from the IoTConnect platform "Settings->Key Vault". 
 * interval          :: send data frequency in seconds
 * sdkOptions        :: It helps to define the path of self signed and CA signed certificate as well as define the offlinne storagr params
"""

env = "<<env>> "
uniqueId = "<<uniqueId>>"
cpId = "<<CPID>>"
scopeId = "<<your scopeId>>"
sdk=None
interval = 30

tProcess = None
dtoc=[]

"""
 * sdkOptions is optional. 
 * "offlineStorage" : Define the configuration related to the offline data storage 
 * 	- disabled : false = offline data storing, true = not storing offline data 
 * 	- availSpaceInMb : Define the file size of offline data which should be in (MB)
 * 	- fileCount : Number of files need to create for offline data
 * Note: sdkOptions is optional. Define proper setting or leave it NULL. If you not provide the offline storage it will set the default settings as per defined above. It may harm your device by storing the large data. Once memory get full may chance to stop the execution.
"""

sdkOptions={
    "certificate":None,
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

def DeviceCallback(msg):
    global dtoc
    print("\n--- Command Message Received ---")
    print(json.dumps(msg))
    cmdType = None
    if msg != None and len(msg.items()) != 0:
        cmdType = msg["cmdType"] if msg["cmdType"] != None else None
    # Other Command
    if cmdType == "0x01":
        """
        * Type    : Public Method "sendAck()" *This mathod in main()
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
            dtoc.append(d2cMsg) # 5 : command acknowledgement
    # Firmware Upgrade
    elif cmdType == "0x02":
        """
        * Type    : Public Method "sendAck()" *This mathod in main()
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
                dtoc.append(d2cMsg) # 11 : Firmware acknowledgement
            else:
                d2cMsg={
                    "ackId" : data["ackId"],
                    "st" : 7,
                    "msg" : "OTA updated successfully..!!",
                    "childId" : ''
                }
                dtoc.append(d2cMsg) # 11 : Firmware acknowledgement
                
    elif cmdType == "0x16":
        data = msg
        if data["command"] == "True":
            print("device connected..")
        else:
            print("device disconnected..")

"""
 * Type    : Callback Function "TwinUpdateCallback()"
 * Usage   : Manage twin properties as per business logic to update the twin reported property
 * Input   : 
 * Output  : Receive twin Desired and twin Reported properties
"""

def TwinUpdateCallback(msg):
    global sdk
    if msg:
        print("\n--- Twin Message Received ---")
        print(json.dumps(msg))
        if ("desired" not in msg) and ("reported" not in msg):
            for j in msg:
                if ("version" not in j) and ("uniqueId" not in j):
                    sdk.UpdateTwin(j,msg[j])
        elif ("desired" in msg) and ("reported" in msg):
            for j in msg["desired"]:
                if ("version" not in j) and ("uniqueId" not in j):
                    if msg["desired"][j] != msg["reported"][j]:
                        sdk.UpdateTwin(j,msg["desired"][j])
        #print(json.dumps(msg))

"""
 * Type    : Public Method "UpdateTwin()"
 * Usage   : Update the twin reported property
 * Input   : Desired property "key" and Desired property "value"
 * Output  : 
"""
# key = "<< Desired property key >>"; // Desired proeprty key received from Twin callback message
# value = "<< Desired Property value >>"; // Value of respective desired property
# sdk.UpdateTwin(key,value)

"""
 * Type    : Public data Method "SendData()"
 * Usage   : To publish the data on cloud D2C 
 * Input   : Predefined data object 
 * Output  : 
"""
def sendBackToSDK(_sdk, dataArray):
    global tProcess
    _sdk.SendData(dataArray)
    time.sleep(interval)
    tProcess = None

def main():
        global tProcess,cpId,uniqueId,env,sdkOptions,sdk,dtoc
        #try:
        
        """
        * Type    : Object Initialization "IoTConnectSDK()"
        * Usage   : To Initialize SDK and Device cinnection
        * Input   : cpId, uniqueId, sdkOptions, env as explained above and DeviceCallback and TwinUpdateCallback is callback functions
        * Output  : Callback methods for device command and twin properties
        """
        #print ("before iotconnect sdk")
        with IoTConnectSDK(cpId, uniqueId,scopeId, DeviceCallback, TwinUpdateCallback, sdkOptions, env) as sdk:
            try:
                #sdk.GetAttributes()
                while True:
                    dataArray=[]

                    
                    #* Non Gateway device input data format Example:

                    data = {"CpuTemperature":random.randint(20,50)}


                    dObj = {
                        "uniqueId": uniqueId,
                        "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                        "data": data
                    }

                    """
                    * Gateway device input data format Example:
                    * dObj = {
                    *     "uniqueId":uniqueId,
                    *     "time":datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),,
                    *     "data": {}
                    * },{
                    *     "uniqueId":uniqueId,
                    *     "time":datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),,
                    *     "data": {}
                    * }
                    """
                    """
                    * Add your device attributes and respective value here as per standard format defined in sdk documentation
                    * "time" : Date format should be as defined //"2021-01-24T10:06:17.857Z" 
                    * "data" : JSON data type format // {"temperature": 15.55, "gyroscope" : { 'x' : -1.2 }}
                    """
                    dataArray.append(dObj)     
                    sendBackToSDK(sdk, dataArray)
                    
                    if len(dtoc):
                        #print "dtoc: ",dtoc
                        for i in dtoc:
                            if i["st"] == 6:
                                sdk.SendAck(i,5)
                            elif i["st"] == 7:
                                sdk.SendAck(i,11)
                        dtoc=[]
            except KeyboardInterrupt:
                sys.exit(0)
    #except Exception as ex:
    #    print(ex)
    #    sys.exit(0)

if __name__ == "__main__":
    main()
