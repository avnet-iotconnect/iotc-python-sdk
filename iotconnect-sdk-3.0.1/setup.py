import os
import time
import site
import sys
from setuptools import setup

version_flag = False 
version_selection = "2.7"
packages_requires = []


def Download_URL(URL):
    os.system('git clone ' + URL)


if 'linux' in sys.platform:
    version = (str(sys.version_info[0])+"."+str(sys.version_info[1]))
    #print (version)
    if version == "2.7":
        #python 2.7 packages
        print ('Downloading python 2.7 packages')
        isdir = os.path.isdir("package_2.7")
        #print (isdir)
        if isdir:
            os.system('rm -r package_2.7')
        Download_URL("https://github.com/ms-missing-tpm-package/package_2.7.git")
        version_flag = True 
        version_selection = "2.7"
        os.system('pip install paho-mqtt')
        os.system('pip install ntplib')
        os.system('pip install wheel')
        #packages_requires=["paho-mqtt","ntplib","wheel"]
    elif version == "3.5":
        #python 3.5 packages
        print ('Downloading python 3.5 packages')
        isdir = os.path.isdir("package_3.5")
        if isdir:
            os.system("rm -r package_3.5")
        Download_URL("https://github.com/ms-missing-tpm-package/package_3.5.git")
        version_flag = True 
        version_selection = "3.5"
        packages_requires=["paho-mqtt","ntplib","wheel","jsonlib-python3"]
    else:
        print ('IoTConnect Python TPM SDK supports only python 2.7 or python 3.5 version')    
else:
    print ('IoTConnect TPM SDK will work on Linux OS only')


if version_flag == True:
    time.sleep(10)

    my_path=''
    path=site.getsitepackages()

    if len(path)==1:
        my_path = path
    else:
        i=0
        while i < len(path):
            if "local" in path[i]:
               my_path= path[i]
            i += 1

    if len(path) and my_path == '':
       my_path = path[0]
    print(my_path)
    
    #azure_iothub_device_client-1.4.6.dist-info 
    os.system('cp -R package_'+version_selection+'/azure_iothub_device_client-1.4.6.dist-info '+my_path +'/')

    #iothub_client 
    os.system('cp -R package_'+version_selection+'/iothub_client '+my_path +'/')

    #azure_iot_provisioning_device_client-1.4.6.dist-info
    os.system('cp -R package_'+version_selection+'/azure_iot_provisioning_device_client-1.4.6.dist-info '+my_path +'/')

    #provisioning_device_client
    os.system('cp -R package_'+version_selection+'/provisioning_device_client '+my_path +'/')
    os.system('rm -r package_'+version_selection)
    print ('moved packages to ' +my_path+' folder sucessful')
    #os.system('pip list')
    setup(
        name="iotconnect-sdk",
        version="3.0.1",
        python_requires=">=2.7,>=3.5,<3.7",
        description='SDK for D2C and C2D communication',
        license="MIT",
        author='SOFTWEB SOLUTIONS<admin@softwebsolutions.com> (https://www.softwebsolutions.com)',
        packages=["iotconnect", "iotconnect.client", "iotconnect.common"],
        install_requires=packages_requires,
        package_data={'iotconnect': ['assets/*.*']},
        platforms=['Linux', 'Mac OS X', 'Win'],
        zip_safe=False,
        classifiers=[
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "License :: MIT License",
        "Operating System :: OS Independent"
        ],
    )



