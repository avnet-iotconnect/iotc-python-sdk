# IOTConnect SDK: iotconnect-python-sdk-tpm

This is an PYTHON SDK library to connect the device with IoTConnect cloud by MQTT protocol. This library only abstract JSON responses from both end D2C and C2D. This SDK supports TPM based authentication to communicate with cloud.

## Features:

* The SDK supports to send telemetry data and receive commands from IoTConnect portal.
* User can update firmware Over The Air using "OTA update" Feature supported by SDK.
* SDK support TPM authentication.  
* SDK consists of Gateway device with multiple child devices support.
* SDK supports to receive and update the Twin property. 
* SDK supports device and OTA command Acknowledgement.
* Edge device support with data aggregation.
* Provide device connection status receive by command.
* Support hard stop command to stop device client from cloud.
* It allows sending the OTA command acknowledgment for Gateway and child device.
* It manages the sensor data sending flow over the cloud by using data frequency("df") configuration.
* It allows to disconnect the device from firmware.

# Example Usage:

Import library
```python
from iotconnect import IoTConnectSDK
```

- Prerequisite standard configuration data 
```python
scopeId=<<your scopeId>>
uniqueId = <<uniqueId>>
cpid = <<CPID>> 
env = <<env>> 
```
"uniqueId" 	: Your device uniqueId
"cpId" 		: It is the company code. It gets from the IoTConnect UI portal "Settings->Key Vault"
"env" 		: It is the UI platform environment. It gets from the IoTConnect UI portal "Settings->Key Vault"
"scopeId"   : It need to get from the IoTConnect platform "Settings->Key Vault->DPS Info".

- SdkOptions is for the SDK configuration and needs to parse in SDK object initialize call. You need to manage the below configuration as per your device authentication type.
```json
sdkOptions = {
	"offlineStorage": { 
		"disabled": false, //default value = false, false = store data, true = not store data 
		"availSpaceInMb": 1, //size in MB, Default value = unlimted
		"fileCount": 5 // Default value = 1
	}
}
```
"offlineStorage" : Define the configuration related to the offline data storage 
	- disabled : false = offline data storing, true = not storing offline data 
	- availSpaceInMb : Define the file size of offline data which should be in (MB)
	- fileCount : Number of files need to create for offline data
Note: sdkOptions is optional.If you do not provide offline storage, it will set the default settings as per defined above. It may harm your device by storing the large data. Once memory gets full may chance to stop the execution.


- To initialize the SDK object need to import below sdk package
```python
IoTConnectSDK(cpId, uniqueId, scopeId , DeviceCallback, TwinUpdateCallback, sdkOptions, env) as sdk:
```

- To receive the command from Cloud to Device(C2D).	
```python
def DeviceCallback(msg):
	if(data["cmdType"] == "0x01")
		// Device Command
	elif(data["cmdType"] == "0x02")
		// Firmware Command
	elif(data["cmdType"] == "0x16")
		// Device connection status Command
```

- To receive the twin from Cloud to Device(C2D).
```python
def TwinUpdateCallback(msg):
	print(msg)
```

- To get the list of attributes with respective device.
```python
sdk.GetAttributes();
```

- This is the standard data input format for Gateway and non Gateway device to send the data on IoTConnect cloud(D2C).
```json
# For Non Gateway Device 
data = [{
	"uniqueId": "<< Device UniqueId >>",
	"time" : "<< date >>",
	"data": {}
}];

# For Gateway and multiple child device 
data = [{
	"uniqueId": "<< Gateway Device UniqueId >>", // It should be must first object of the array
	"time": "<< date >>",
	"data": {}
},
{
	"uniqueId":"<< Child DeviceId >>", //Child device
	"time": "<< date >>",
	"data": {}
}]
sdk.SendData(data);
```
"time" : Date format should be as defined #"2021-01-24T10:06:17.857Z" 
"data" : JSON data type format # {"temperature": 15.55, "gyroscope" : { 'x' : -1.2 }}


- To send the command acknowledgment
```python
d2cMsg = {
	"ackId": data["ackId"],
	"st": Acknowledgment status sent to cloud
	"msg": "", it is used to send your custom message
	"childId": "" it is use for gateway's child device OTA update
}
```
- ackId(*) : Command ack guid which is receive from command payload
- st(*) : Acknowledgment status sent to cloud (4 = Fail, 6 = Device command[0x01], 7 = Firmware OTA command[0x02])
- msg : Message 
- childId : 
	0x01 : null or "" for Device command  
	0x02 : null or "" for Gateway device and mandatory for Gateway child device's OTA udoate.
		   How to get the "childId" .?
		   - You will get child uniqueId for child device OTA command from payload "data.urls[~].uniqueId"
Note : (*) indicates the mandatory element of the object.

- Message Type
```python
msgType = 5  # for "0x01" device command 
msgType = 11 # for "0x02" Firmware OTA command 
sdk.SendAck(self,data,msgType) # msgType:- 11 and 5
```
- To update the Twin Property
```python
key = "<< Desired property key >>"
value = "<< Desired Property value >>"
sdk.UpdateTwin(key,value)
```
"key" 	:	Desired property key received from Twin callback message
"value"	:	Value of the respective desired property

- To disconnect the device from the cloud
```python
sdk.Dispose()
```
- To get the all twin property Desired and Reported
  Note: This feature is not supported from Azure packages.
  
# Dependencies:
* This SDK used below packages :
	Linux OS:-
		- paho-mqtt, ntplib, wheel, azure-iot-provisioning-device-client, azure-iothub-device-client, jsonlib-python3
	windows OS:
		- ntplib, pypiwin32, wheel, azure-iot-provisioning-device-client, azure-iothub-device-client

# Integration Notes:

## Prerequisite tools

1. Python version compatibility
   - Linux Only: Python version 2.7, and 3.5 
2. pip : pip is compatible to the python version
3. setuptools : Required to install IOTConnect SDK

## Installation:

1. Extract the "iotconnect-python-tpm-sdk-v3.0.1.zip"

2. If already exist the IoTConnect python SDK installed in your device then you need to uninstall old version before going to install updated version. 
	- Note : make sure which pip you are use for install package that you have to use for uninsall (pip,pip3)
	- pip list 
    - find your package name(iotconnect-sdk)
    - pip uninsall <<package name>>

3. To install the required libraries use the below command:
	Installation for python version 2.7:
		- Goto SDK directory path using terminal/Command prompt
		- cd iotconnect-python-tpm-sdk-v3.0.1/
		- tar xvfz iotconnect-sdk-3.0.1.tar.gz
		- cd iotconnect-sdk-3.0.1
		- python setup.py install

	Installation for python version 3.5:
		- Goto SDK directory path using terminal/Command prompt
		- cd iotconnect-python-tpm-sdk-v3.0.1/
		- pip3 install iotconnect-sdk-3.0.1.tar.gz

4. Using terminal/command prompt goto sample folder
	- cd /iotconnect-python-tpm-sdk-v3.0.1/sample/ 

5. You can take the firmware file from the above location and update the following details
	- Prerequisite input data as explained in the usage section as below
	- Update sensor attributes according to added in IoTConnect cloud platform.

6. Ready to go:
	- Python 2.7: python iotconnect-tpm-sdk-firmware-python-3.0.1.py
	- python 3.5: python3 iotconnect-tpm-sdk-firmware-python-3.0.1.py

## Release Note :

** New Feature **
1. Offline data storage functionality with specific settings
2. Edge enable device support Gateway device too
3. Device and OTA command acknowledgment
4. It allows to disconnect the device client 
5. Introduce new methods:
	Dispose() : to disconnect the device
	UpdateTwin() : To update the twin properties from device to cloud
6. Support hard stop command to stop device client from cloud
7. Support OTA command with Gateway and child device
8. It allows sending the OTA command acknowledgment for Gateway and child device
9. Introduce new command(0x16) in device callback for Device connection status true(connected) or false(disconnected)

** Improvements **
1. We have updated the below methods name:
   To Initialize the SDK object:
	- Old : IoTConnectSDK(cpid, uniqueId, callbackMessage, twinCallbackMessage, env)
	- New : IoTConnectSDK(cpId, uniqueId, scopeId, DeviceCallback, TwinUpdateCallback, sdkOptions, env)
   To update the Twin Reported Property :
    - New : UpdateTwin(key, value)
   To receive Device command callback :
    - Old : callbackMessage(data);
	- New : DeviceCallback(data);
   To receive OTA command callback :
    - Old : twinCallbackMessage(data);
	- New : TwinUpdateCallback(data);
2. Update the OTA command receiver payload for multiple OTA files
3. Use the "df" Data Frequency feature to control the flow of data which publish on cloud (For Non-Edge device only).
4. Remove "properties.json" file and use the sdkOptions for the offline data storage configuration.