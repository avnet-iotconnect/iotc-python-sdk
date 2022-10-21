# Softweb Solutions Inc
## IOT Connect SDK : Software Development Kit 1.0

**Prerequisite tools:**

1. Python : Python version 2.7, 3.6, 3.7, and 3.8
2. pip : pip is compatible to the python version
3. setuptools : It Requires to manage the python packages.

**Installation :** 

1. Extract the "iotconnect-python-sdk-v1.0.zip" downloaded package

2. If already exist the IoTConnect python SDK installed in your device then you need to uninstall old version before going to install updated version. 
	- Note : make sure which pip you are use for install package that you have to use for uninsall (pip,pip3)
	- pip list 
    - find your package name(iotconnect-sdk)
    - pip uninsall <<package name>>    
	
3. To install the required libraries use the below command:
	- Goto SDK directory path using terminal/Command prompt
	- cd iotconnect-python-sdk-v1.0/
    - Python version 3.x :
		- pip3 install iotconnect-sdk-1.0.tar.gz
	- Python version 2.7 :
		- Extract the iotconnect-sdk-1.0.tar.gz
		- cd iotconnect-sdk-1.0/
		- python setup.py install		

4. Using terminal/command prompt goto sample folder
	- cd sample/
	
5. You can take the firmware file from the above location and update the following details
	- Prerequisite input data as explained in the usage section as below
	- Update sensor attributes according to added in IoTConnect cloud platform
	- If your device is secure then need to configure the x.509 certificate path as like sdkOptions given below otherwise leave as it is.

6. Ready to go:
	- Python 2.7 : 
		- python iotconnect-sdk-1.0-firmware-python_msg-2_1.py (This script send the data on the cloud as per configured device detail)
	- Python 3.x : 
		- python3 iotconnect-sdk-1.0-firmware-python_msg-2_1.py (This script send the data on the cloud as per configured device detail)
	
** Usage :**

- To initialize the SDK object need to import below sdk package
```python
from iotconnect import IoTConnectSDK
```

- Prerequisite standard configuration data 
```python
UniqueId = "<<Device UniqueID>>"
SId = "<<Your SID>>"
```
"uniqueId" 	: Your device uniqueId
"SId" 		: It is the company code. It gets from the IoTConnect UI portal "Settings->Key Vault -> SDK Identities -> select language Python and Version 1.0"

- SdkOptions is for the SDK configuration and needs to parse in SDK object initialize call. You need to manage the below configuration as per your device authentication type.
```python
sdkOptions = {
    "certificate" : { #For SSL CA signed and SelfSigned authorized device only
        "SSLKeyPath"	: "<< SystemPath >>/device.key",
		"SSLCertPath"   : "<< SystemPath >>/device.pem",
		"SSLCaPath"     : "<< SystemPath >>/rootCA.pem"
	},
    "offlineStorage": { 
		"disabled": false, #default value = false, false = store data, true = not store data 
		"availSpaceInMb": 1, #size in MB, Default value = unlimited
		"fileCount": 5 # Default value = 1
	},
	"devicePrimaryKey": "<<your Key>>" # For Symmetric Key Authentication type support
	
}
```
"certificate": It is indicated to define the path of the certificate file. Mandatory for X.509/SSL device CA signed or self-signed authentication type only.
	- SSLKeyPath: your device key
	- SSLCertPath: your device certificate
	- SSLCaPath : Root CA certificate
"offlineStorage" : Define the configuration related to the offline data storage 
	- disabled : false = offline data storing, true = not storing offline data 
	- availSpaceInMb : Define the file size of offline data which should be in (MB)
	- fileCount : Number of files need to create for offline data
"devicePrimaryKey" : It is optional parameter. Mandatory for the Symmetric Key Authentication support only. It gets from the IoTConnect UI portal "Device -> Select device -> info(Tab) -> Connection Info -> Device Connection -> primaryKey".
    
Note: SdkOptions is optional but mandatory for SSL/x509 device authentication type only. Define proper setting or leave it NULL. If you do not provide offline storage, it will set the default settings as per defined above. It may harm your device by storing the large data. Once memory gets full may chance to stop the execution.

- To Initialize the SDK object and connect to the cloud
```python
	with IoTConnectSDK(UniqueId,SId,SdkOptions,DeviceConectionCallback) as Sdk:
```

- To register Direct Method
```python
   regiter_directmethod_callback(methodname,DirectMethodCallback)
``` 

- To receive the command from Cloud to Device(C2D)	
```python
	def DeviceCallback(msg):
		if(data["cmdType"] == "0x01")
			# Device Command
		if(data["cmdType"] == "0x02")
			# Firmware Command
		if(data["cmdType"] == "0x16")
			# Device connection status e.g. data["command"] = true(connected) or false(disconnected)
```

- To receive the twin from Cloud to Device(C2D)
```python
	def TwinUpdateCallback(msg):
		print(msg)
```

- To receive Direct Method from cloud 
```python 
	def DirectMethodCallback(msg,rId):
        print(msg)
        print(rId)
        data={"data":"fail"}        
```

- To get the list of attributes with respective device.
```python
	devices=sdk.GetAttributes()
```

- This is the standard data input format for Gateway and non Gateway device to send the data on IoTConnect cloud(D2C).
```python
1. For Non Gateway Device 
data = [{
    "uniqueId": "<< Device UniqueId >>",
    "time" : "<< date >>",
    "data": {}
}]

2. For Gateway and multiple child device 
data = [{
	"uniqueId": "<< Gateway Device UniqueId >>", # It should be first element
	"time": "<< date >>",
	"data": {}
},
{
	"uniqueId":"<< Child DeviceId >>", #Child device
	"time": "<< date >>",
	"data": {}
}]
sdk.SendData(data)
```
"time" : Date format should be as defined #"2021-01-24T10:06:17.857Z" 
"data" : JSON data type format # {"temperature": 15.55, "gyroscope" : { 'x' : -1.2 }}

- To send the command acknowledgment
```python
	data = {
		"ackId": data.ackId,
		"st": ""
		"msg": "",
		"childId": ""
	}
	msgType = ""; # 5 ("0x01" device command), 11 ("0x02" Firmware OTA command)
    sdk.SendAck(data, msgType) # msgType:- 11 and 5
```
"ackId(*)" 	: Command Acknowledgment GUID which will receive from command payload (data.ackId)
"st(*)"		: Acknowledgment status sent to cloud (4 = Fail, 6 = Device command[0x01], 7 = Firmware OTA command[0x02])
"msg" 		: It is used to send your custom message
"childId" 	: It is used for Gateway's child device OTA update only
				0x01 : null or "" for Device command
			  	0x02 : null or "" for Gateway device and mandatory for Gateway child device's OTA update.
		   		How to get the "childId" .?
		   		- You will get child uniqueId for child device OTA command from payload "data.urls[~].uniqueId"
"msgType" 	: Message type (5 = "0x01" device command, 11 = "0x02" Firmware OTA command)
Note : (*) indicates the mandatory element of the object.

- To Send Direct Method Acknowledgment 
```python
DirectMethodACK(data,200,rId) #Status should be 200
```
Data    : It is your message and message should be in JSON 
status  : 200 
rid     : Your request ID, you will get from DirectMethodCallback() 

- To update the Twin Property
```python
	key = "<< Desired property key >>"
	value = "<< Desired Property value >>"
    sdk.UpdateTwin(key, value)
```
"key" 	:	Desired property key received from Twin callback message
"value"	:	Value of the respective desired property

- To disconnect the device from the cloud
```python
	sdk.Dispose()
```

- To get the all twin property Desired and Reported
```python
	sdk.GetAllTwins();
```


## Release Note :

** New Feature **

** Improvements **


