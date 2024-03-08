Instructions for the running the Python SDK (https://github.com/avnet-iotconnect/iotc-python-sdk/tree/master-std-21) on Windows:

# Primary Tasks
1) Install Python
2) Install Visual Studio

## Install Python (<= 3.9)
* Download and Install Python:  https://www.python.org/downloads/release/python-379/
* Download and extract the SDK:  https://github.com/avnet-iotconnect/iotc-python-sdk/archive/refs/heads/master-std-21.zip

* Open a command prompt:  Click "Start" and type `cmd`

Verify that python is installed and the environment variables for Path are set properly by entering:  
`python –version` or `python3 –version`

Update pip:  
`c:\python\python.exe -m pip install --upgrade pip`  

Install Wheel:  
`c:\python\python.exe -m pip install wheel`

## Install Microsoft Visual Studio:
* Download VS: https://visualstudio.microsoft.com/downloads/
  *	Install the C++ build package
  * Include Windows SDK and the "MSVC v142 - VS 2019 C++ x64/x86" build tools during installation.

## Start the SDK Installation
*	Go to SDK directory path using the terminal/command prompt  
`cd iotconnect-python-sdk-v1.0/`  
*	Run the SDK Installation  
`pip3 install iotconnect-sdk-1.0.tar.gz`

## Create a Template, Device, and Generate Certificates:  
*	Follow steps 1 and 2 from this guide:  
  https://github.com/avnet-iotconnect/iotc-python-examples/blob/main/DELL_3200_5200_Demo/README.md  
  *	Note, you will stay pointed to the instance you were given, commonly avnet.iotconnect.io
  *	Name the device with a unique identifier of your choosing and will be using an x.509 certificate.
  * Add an attribute to the template to get started ("temp" or "version" as examples).  The template can always be updated later with the attributes defined in your script.
  * Most importantly, ensure to download the certificates.

## Modify the sample python script
*	The sample script is named “iotconnect-sdk-1.0-firmware-python_msg-2_1.py” and is located where you unzipped the SDK package within the sample sub directory.  
*	Add your Security certificate file locations and your Unique ID and SID.  
*	Security Certificates go here:
![image](https://github.com/avnet-iotconnect/iotc-python-sdk/assets/40640041/43628bd1-9541-4eac-9322-b34ae681342a)  


•	"UniqueId" : Your device uniqueID
•	"SId" : SId is the company code. You can get it from the IoTConnect UI portal “Settings -> Key Vault -> SDK Identities -> select language Python and Version 1.0”
![image](https://github.com/avnet-iotconnect/iotc-python-sdk/assets/40640041/04854dfc-fd52-408c-b906-afca64957b87)  


* If you want to pull some interesting metrics from your PC, you can install the psutil library on your windows machine.  
`pip install psutil`  

In your sample python script, include the library:  
`import psutil`
 
and then within the Main function:  
![image](https://github.com/avnet-iotconnect/iotc-python-sdk/assets/40640041/dc0fd03b-4a5a-4b9a-a7ff-0b9fd428517c)  

You can then run your script from the windows cmd:  
`cd sample`  
`python iotconnect-sdk-1.0-firmware-python_msg-2_1.py`  
![image](https://github.com/avnet-iotconnect/iotc-python-sdk/assets/40640041/7ac37f4c-d6b7-4fe8-91f6-d294aacc824c)
