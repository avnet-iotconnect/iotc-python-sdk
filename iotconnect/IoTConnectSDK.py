import sys
import json
import os.path
from pathlib import Path
import copy
import time
import threading
import ssl
import ntplib
import urllib
from urllib.parse import quote_plus, urlencode
import datetime
from threading import Timer
from base64 import b64encode, b64decode
from hashlib import sha256
from hmac import HMAC

import iotconnect.config as config

from iotconnect.client.mqttclient import mqttclient
from iotconnect.client.httpclient import httpclient
from iotconnect.client.offlineclient import offlineclient

from iotconnect.common.data_evaluation import data_evaluation
from iotconnect.common.rule_evaluation import rule_evaluation

from iotconnect.common.infinite_timer import infinite_timer

from iotconnect.IoTConnectSDKException import IoTConnectSDKException

MSGTYPE = {
    "RPT": 0,
    "FLT": 1,
    "RPTEDGE": 2,
    "RMEdge": 3,
    "LOG" : 4,
    "ACK" : 5,
    "OTA" : 6,
    "FIRMWARE": 11
}
ErorCode = {
    "OK": 0,
    "DEV_NOT_REG": 1,
    "AUTO_REG": 2,
    "DEV_NOT_FOUND": 3,
    "DEV_INACTIVE": 4,
    "OBJ_MOVED": 5,
    "CPID_NOT_FOUND": 6
}
CMDTYPE = {
    "DCOMM": 0,
    "FIRMWARE": 1,
    "MODULE":2,
    "U_ATTRIBUTE": 101,
    "U_SETTING": 102,
    "U_RULE": 103,
    "U_DEVICE": 104,
    "DATA_FRQ": 105,
    "U_barred":106,
    "D_Disabled":107,
    "D_Released":108,
    "STOP":109,
    "Start_Hr_beat":110,
    "Stop_Hr_beat":111,
    "is_connect": 116,
    "SYNC": "sync",
    "RESETPWD": "resetpwd",
    "UCART": "updatecrt"
}

OPTION = {
    "attribute": "att",
    "setting": "set",
    "protocol": "p",
    "device": "d",
    "sdkConfig": "sc",
    "rule": "r"
}
DATATYPE = {
    1: "INT",
    2:"LONG",
    3:"FLOAT",
    4:"STRING",
    5:"Time",
    6:"Date",
    7:"DateTime",
    8:"BIT",
    9:"Boolean",
    10:"LatLong",
    11:"OBJECT"
}

class IoTConnectSDK:
    # Device and company details
    _cpId = None
    _sId = None
    _uniqueId = None

    # SDK Options. get's merged into _config 
    _property = None

    # config.json from assets folder
    _config = None

    # Callback functions
    _listner_callback = None
    _listner_ota_callback = None
    _listner_device_callback = None
    _listner_attchng_callback = None
    _listner_module_callback = None
    _listner_devicechng_callback = None
    _listner_rulechng_callback = None
    _listner_creatchild_callback = None
    _listner_twin_callback = None

    _getattribute_callback = None

    # Stores JSON data from a cloud message (?)
    _data_json = None

    # MQTT / HTTP Client Object
    _client = None

    _is_process_started = False

    # Stores the base url of the identity API retrieved from discovery
    _identity_base_url = ""


    _thread = None
    _ruleEval = None
    _offlineClient = None
    _lock = None

    _live_device=[]
    _debug=False
    _data_frequency = 60
    _debug_error_path=None
    _debug_output_path=None
    _dftime=None
    _offlineflag = False
    _time_s=None
    _heartbeat_timer = None
    deletechild=None
    _listner_deletechild_callback = None

    # Validation flag. True if data validation is enabled
    _validation = True

    # Loads the config.json file from the assets folder
    def _get_config(self):
        config_path = Path("iotconnect/assets/config.json")
        try:
            with open(config_path) as config_file:
                self._config = json.loads(config_file.read())
            self._config.update(self._property)
        except:
            raise IOError("Missing config.json file in assets folder.")

    def getTwins(self):
        if self._is_process_started == False:
            return
        if self._client:
            self._client.get_twin()

    def reconnect_device(self,msg):
        # print(msg)
        try:
            self.process_sync("all")
        except:
            self._offlineflag = True

    def __get_discovery_url(self, baseURL, sId):
        return f"{baseURL}/api/v2.1/dsdk/sid/{sId}"

    # Makes a request to the discovery API with the provided base url and sId
    def __discover(self, discoveryBaseURL, sId):
        try:
            discovery_request_url = self.__get_discovery_url(discoveryBaseURL, sId)
            res = urllib.request.urlopen(discovery_request_url).read().decode("utf-8")
            data = json.loads(res)
            # If platform is specified
            if 'pf' in data['d'].keys():
                return data['d']["bu"], data['d']["pf"]
            # Else set to azure by default
            else:
                return data['d']["bu"], 'az'

        except Exception as ex:
            print (ex.message)
            return None

    def generate_sas_token(self,uri, key, policy_name=None, expiry=31536000):
        ttl = time.time() + expiry
        sign_key = "%s\n%d" % ((quote_plus(uri)), int(ttl))
        signature = b64encode(HMAC(b64decode(key), sign_key.encode('utf-8'), sha256).digest())
        rawtoken = {
            'sr' :  uri,
            'sig': signature,
            'se' : str(int(ttl))
        }
        if policy_name is not None:
            rawtoken['skn'] = policy_name
        return 'SharedAccessSignature ' + urlencode(rawtoken)



    def post_call(self, url):
        try:
            url=url+"/uid/"+self._uniqueId
            print(f"URL: {url}")
            res = urllib.request.urlopen(url).read().decode("utf-8")
            return json.loads(res)
        except:
            return None

    # The following command functions are used to set the callback functions
    # TODO: this can be reduced to a single functions with the module as a parameter
    def onOTACommand(self,callback):
        if callback:
            self._listner_ota_callback = callback

    def onModuleCommand(self,callback):
        if callback:
            self._listner_module_callback = callback

    def onDeviceCommand(self,callback):
        if callback:
            self._listner_device_callback = callback

    def onTwinChangeCommand(self,callback):
        if callback:
            self._listner_twin_callback = callback

    def onAttrChangeCommand(self,callback):
        if callback:
            self._listner_attchng_callback = callback

    def onDeviceChangeCommand(self,callback):
        if callback:
            self._listner_devicechng_callback=callback

    def onRuleChangeCommand(self,callback):
        if callback:
            self._listner_rulechng_callback = callback

    # Start and Stop the heartbeat
    def heartbeat_stop(self):
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None

    def heartbeat_start(self,time):
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
        if self._client:
            self._heartbeat_timer=infinite_timer(time,self._client.send_HB)
            self._heartbeat_timer.start()

    # Called when a message is received from the cloud
    def onMessage(self, msg):
        try:
            if msg == None:
                return
             
            self._is_process_started = True

            if "data" in msg and msg["data"]:
                msg=msg["data"]
            if "d" in msg and msg["d"]:
                msg=msg["d"]
                print(msg)
                if msg['ec'] == 0:
                    if msg["ct"] == 201:
                        if self._getattribute_callback == None:
                            self._data_json["att"] = msg["att"]
                            for attr in self.attributes:
                                attr["evaluation"] = data_evaluation(self.isEdge, attr, self.send_edge_data)
                            self._is_process_started = True
                            self._offlineflag=False
                            print("..........Atrributes Get Successfully...........")
                        if self._getattribute_callback:
                            self._getattribute_callback(msg["att"])
                            self._getattribute_callback = None

                    if msg["ct"] == 202:
                        self._data_json["set"] = msg["set"]
                    if msg["ct"] == 203:
                        self._data_json["r"] = msg["r"]
                    if msg["ct"] == 204 and len(msg['d']) != 0:
                        self._data_json['d']=[]
                        self._data_json['d'].append({'tg': self._data_json['meta']['gtw']['tg'],'id': self._uniqueId})
                        for i in msg["d"]:
                                self._data_json['d'].append(i)
                        if self._listner_devicechng_callback:
                            self._listner_devicechng_callback(msg)
                    if msg["ct"] == 205:
                        self._data_json["ota"] = msg["ota"]
                if msg["ct"] == 221:
                    if self._listner_creatchild_callback:
                        self._listner_creatchild_callback({"status": msg["ec"] == 0,"message":self.__child_error_log(msg["ec"])})
                if msg["ct"] == 222:
                    if self._listner_deletechild_callback:
                        if msg["ec"] == 0:
                            self._listner_deletechild_callback({"status":True,"message":"sucessfuly delete child device"})
                            for i in range(0,len(self._data_json["d"])):
                                if self._data_json["d"][i]["ename"] == self.deletechild:
                                    self._data_json["d"].pop(i)
                                    break
                        else:
                            self._listner_deletechild_callback({"status":True,"message":"fail to delete child device"})
                    self._listner_deletechild_callback=None
                return
            else:
                pass

            if self._is_process_started == False:
                return
            if "ct" not in msg:
                print("Command Received : " + json.dumps(msg))
                return
            _tProcess = None

            ct_code = msg["ct"]

            if ct_code in CMDTYPE:
                print(f"{ct_code} {config.CLOUD_TO_DEVICE_CODES[ct_code]} command received...")
            else:
                raise Exception("Invalid command type code in message.")

            command = config.CLOUD_TO_DEVICE_CODES[ct_code]

            if command == "U_ATTRIBUTE":
                if self._listner_attchng_callback:
                    self._listner_attchng_callback(msg)
                _tProcess = self.reset_process_sync("ATT")
            elif command == "Stop_Hr_beat":
                self.heartbeat_stop()
            elif command == "Start_Hr_beat":
                HBtime=msg["f"]
                self.heartbeat_start(HBtime)
            elif command == "U_SETTING":
                _tProcess = self.reset_process_sync("SETTING")
            elif command == "U_DEVICE":
                _tProcess = self.reset_process_sync("DEVICE")
            elif command == "U_RULE":
                if self._listner_rulechng_callback:
                    self._listner_rulechng_callback(msg)
                _tProcess = self.reset_process_sync("RULE")
            elif command == "RESETPWD":
                #try to debuge
                _tProcess = self.reset_process_sync("protocol")
            elif command == "DATA_FRQ":
                self._data_json['meta']["df"]= msg["df"]
                self._data_frequency = msg["df"]
            elif command == "UCART":
                pass
            elif command == "DCOMM":
                if self._listner_device_callback is not None:
                    self._listner_device_callback(msg)
            elif command == "FIRMWARE":
                if self._listner_ota_callback:
                    self._listner_ota_callback(msg)
            elif command == "MODULE":
                if self._listner_module_callback:
                    self._listner_module_callback(msg)
            elif command == "U_barred" or command == "D_Disabled" or command == "D_Released" or command == "STOP":
                # The device must stop all communication and release the MQTT connection
                self._is_process_started=False
                if self._offlineClient:
                    self._offlineClient.clear_all_files()
                if self._client and hasattr(self._client, 'Disconnect'):
                    self._client.Disconnect()
                # print("0x99 command received so device is barred")
            elif command == "is_connect":
                    msg["uniqueId"] = self._uniqueId
                    if msg["command"] in "False":
                        self._offlineflag = True
                        if self._is_process_started:
                            self.reconnect_device("reconnect")

                    if self._listner_callback:
                        self._listner_callback(msg)
                    self.write_debuglog('[INFO_CM09] '+ self._time +'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] 0x116 sdk connection status: " + msg["command"],0)
                    return
            else:
                print("Message : " + json.dumps(msg))

            if _tProcess is not None:
                _tProcess.setName("PSYNC")
                _tProcess.daemon = True
                _tProcess.start()

        except Exception as ex:
            print("Message process failed..."+ str(ex))

    def onTwinMessage(self, msg,value):
        try:
            if self._is_process_started == False:
                return
            #if self.has_key("payload", msg) == False and ((msg.payload == None) or (msg.payload == '')):
            #    return
            #msg = msg.payload.decode("utf-8")
            #if msg == None or len(msg) == 0 :
            #    return
            #msg = json.loads(msg)
            if  value:
                temp=msg
                msg={}
                msg["desired"]=temp
                msg["uniqueId"] = self._uniqueId
            else:
                msg["uniqueId"] = self._uniqueId
            if self._listner_twin_callback is not None:
                self._listner_twin_callback(msg)
        except Exception as ex:
            print("Message process failed...",ex)

    def onDirectMethodMessage(self,msg,methodname,requestId):
        try:
            if self._listner_direct_callback_list :
                self._listner_direct_callback_list[str(methodname)](msg,methodname,requestId)
        except Exception as ex:
            print(ex)

    def set_client(self, name, auth_type, protocol_config):
            # Initializes the client object (mqtt or http)
            if name == "mqtt":
                return mqttclient(auth_type, protocol_config, self._config, self.onMessage,self.onDirectMethodMessage, self.onTwinMessage)
            elif name == "http" or name == "https":
                return httpclient(protocol_config, self._config)
            else:
                raise ValueError("Invalid client type specified.")

    # Runs various initialization steps
    def _init_protocol(self):
        try:
            protocol_config = self.protocol
            print(f"protocol config: {protocol_config}")
            name = protocol_config["n"]
            protocol_config["pf"] = self._pf
            auth_type = self._data_json["meta"]['at']
            if auth_type == 2 or auth_type == 3:
                cert_list=self._config["certificate"]
                if len(cert_list) == 3:
                    for cert_name, cert_path in cert_list.items():
                        if not os.path.isfile(cert_path):
                            self.write_debuglog('[ERR_IN06] '+ self._time +'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] sdkOption: set proper certificate file path and try again",1)
                            raise(IoTConnectSDKException("05", f"{cert_name} certificate specified in SDKOptions Not found"))
                else:
                    self.write_debuglog('[ERR_IN06] '+ self._time +'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] sdkOption: set proper certificate file path and try again",1)
                    raise(IoTConnectSDKException("01","Certificate/Key in Sdkoption"))
                
            self._client = self.set_client(name, auth_type, protocol_config)

            if auth_type == 5:
                if ("devicePrimaryKey" in self._property) and self._property["devicePrimaryKey"]:
                    protocol_config["pwd"]=self.generate_sas_token(protocol_config["h"],self._property["devicePrimaryKey"])
                else:
                    raise(IoTConnectSDKException("01", "devicePrimaryKey"))

        except Exception as ex:
            raise(ex)

    def _hello_handshake(self,data):
        if self._client:
            self._client.Send(data,"Di")

    def __get_device_identity(self, option):
        """Requests information about the provided device from iotconnect"""
        if option not in config.DEVICE_IDENTITY_OPTIONS:
            raise ValueError("Invalid process sync option provided.")
        
        if option == "all":
            url = self._identity_base_url
            response = self.post_call(url)

            if response is None:
                raise Exception("Empty response on get device identity.")


        else:
            self._hello_handshake({"mt": config.DEVICE_IDENTITY_MESSAGES[option], "sid": self._sId}) 

    # This function does a lot and needs to be broken down
    # Seems like it's responsible for connecting and syncing with iotconnect
    def process_sync(self, option):
        print(f"Process Sync: {option}")
        
        
        try:
            self._time_s=10
            isReChecking = False
            if option == "all":
                url = self._identity_base_url
                response = self.post_call(url)
                print(response)
                if response == None:
                    if self._offlineflag == True:
                        isReChecking=True
                    else:
                        raise(IoTConnectSDKException("01", "Sync response"))
                else:
                    if "d" in response:
                        response = response["d"]
                        self.write_debuglog('[INFO_IN01] '+'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] Device information received successfully: "+ self._time ,0)
                        self._offlineflag = False
                    else:
                        raise(IoTConnectSDKException("03", response["message"]))
                    if response["ec"] != ErorCode["OK"]:
                        isReChecking = True
                        self._time_s=60
                    if response["ec"] == ErorCode["DEV_NOT_FOUND"] or response["ec"] == ErorCode["CPID_NOT_FOUND"] :
                        self.write_debuglog('[ERR_IN10] '+ self._time +'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] Device Information not found",1)
            else:
                self.__get_device_identity(option) 

            if isReChecking:
                print("\nDisConnected...")
                print("\nTrying to Connect...")
                _tProcess = self.reset_process_sync(option)
                time.sleep(self._time_s)
                _tProcess.setName("PSYNC")
                _tProcess.daemon = True
                _tProcess.start()
                return
            
            # Pre Process
            self.clear_object(option)
            # --------------------------------
            if option == "all":
                self._is_process_started = False
                self._data_json = response
                self._init_protocol()
                if self._pf == "aws":
                    data = { "_connectionStatus": "true" }
                    self._client.SendTwinData(data)
                    print("\nPublish connection status shadow sucessfully... %s" % self._time)

                print(self._data_json)
                if "has" in self._data_json:
                    if self._data_json["has"]["attr"]:
                        # self._hello_handshake({"mt":201,"sid":self._sId})
                        self._hello_handshake({"mt":201})
                    if self._data_json["has"]["set"]:
                        self._hello_handshake({"mt":202,"sid":self._sId})
                    if self._data_json["has"]["r"]:
                        self._hello_handshake({"mt":203 ,"sid":self._sId})
                    if self._data_json["has"]["d"]:
                        self._hello_handshake({"mt":204,"sid":self._sId})
                    else:
                        self._data_json['d']=[{'tg': '','id': self._uniqueId}]

                    if self._data_json["has"]["ota"]:
                        self._hello_handshake({"mt":205,"sid":self._sId})

                if "df" in self._data_json['meta'] and self._data_json['meta']["df"]:
                    self._data_frequency=self._data_json['meta']["df"]

        except Exception as ex:
            raise ex

    # Returns the number of seconds in H:M:S format?
    def find_df(self,seconds):
        seconds = seconds % (24 * 3600)
        hour = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        times= datetime.datetime.strptime("%02d%02d%02d" % (hour, minutes, seconds),'%H%M%S')
        return times

    # Used to send data to the IoTConnect Cloud
    def SendData(self,jsonArray):
        print(jsonArray)
        print(type(jsonArray))
        try:
            if self._is_process_started == False:
                self.write_debuglog('[ERR_SD04] '+ self._time +'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] Device is barred SendData() method is not permitted",1)
                return
            if "att" not in self._data_json:
                print("\n")
                return

            nowtime=datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            time_zero = datetime.datetime.strptime('000000', '%H%M%S')
            edge_flt_flag = False
            if self._dftime is not None:
                if int(nowtime) >= self._dftime:
                    nowtime=datetime.datetime.strptime(str(nowtime),"%Y%m%d%H%M%S")
                    self._dftime = int((nowtime - time_zero + self.find_df(self._data_frequency)).strftime("%Y%m%d%H%M%S"))
                    if self.isEdge:
                        edge_flt_flag=True
                else:
                    if not self.isEdge:
                        return
            else:
                nowtime=datetime.datetime.strptime(str(nowtime),"%Y%m%d%H%M%S")
                self._dftime = int((nowtime - time_zero + self.find_df(self._data_frequency)).strftime("%Y%m%d%H%M%S"))
                if self.isEdge:
                    edge_flt_flag=True
            #--------------------------------
            rul_data = []
            rpt_data = self._data_template
            flt_data = self._data_template
            for obj in jsonArray:
                rul_data = []
                uniqueId = obj["uniqueId"]
                time = obj["time"]
                sensorData = obj["data"]
                for attr in self.attributes:
                    if "evaluation" in attr:
                        evaluation = attr["evaluation"]
                        evaluation.reset_get_rule_data()
                for d in self.devices:
                    if d["id"] == uniqueId:
                        if uniqueId not in self._live_device:
                            self._live_device.append(uniqueId)
                        if self._data_json['has']['d']:
                            tg = d["tg"]
                            r_device = {
                                "id": uniqueId,
                                "dt": time,
                                "tg": tg
                            }
                        else:
                            r_device = {
                                "dt": time
                            }
                        f_device = copy.deepcopy(r_device)
                        r_attr_s = {}
                        f_attr_s = {}
                        real_sensor=[]
                        for attr in self.attributes:
                            if attr["p"] == "" and "evaluation" in attr:
                                evaluation = attr["evaluation"]
                                evaluation.reset_get_rule_data()
                                for dObj in attr["d"]:
                                    child=True
                                    if self._data_json['has']['d']:
                                        if tg == dObj["tg"]:
                                            pass
                                        else:
                                            child=False
                                    if child and dObj["ln"] in sensorData:
                                        value = sensorData[dObj["ln"]]
                                        real_sensor.append(dObj["ln"])
                                        if self.isEdge:
                                            if type(value) == str:
                                                try:
                                                    sub_value=float(value)
                                                except:
                                                    real_sensor.remove(dObj["ln"])
                                        if value is not None:
                                            row_data = evaluation.process_data(dObj, attr["p"], value,self._validation)
                                            if row_data and "RPT" in row_data:
                                                for key, value in row_data["RPT"].items():
                                                    r_attr_s[key] = value
                                            if row_data and "FLT" in row_data:
                                                for key, value in row_data["FLT"].items():
                                                    f_attr_s[key] = value
                                        else:
                                            pass
                                            #f_attr_s[sensorData[dObj]]
                                data = evaluation.get_rule_data()
                                if data is not None:
                                    rul_data.append(data)

                            elif attr["p"] != "" and "evaluation" in attr and attr["p"] in sensorData:
                                child = True
                                if self._data_json['has']['d']:
                                    if tg == attr["tg"]:
                                        pass
                                    else:
                                        child = False
                                if child:
                                    evaluation = attr["evaluation"]
                                    evaluation.reset_get_rule_data()
                                    real_sensor.append(attr["p"])
                                    sub_sensors=[]
                                    for dObj in attr["d"]:
                                        if dObj["ln"] in sensorData[attr["p"]]:
                                            sub_sensors.append(dObj["ln"])
                                            value = sensorData[attr["p"]][dObj["ln"]]
                                            if self.isEdge:
                                                if type(value) == str:
                                                    try:
                                                        sub_value=float(value)
                                                    except:
                                                        sub_sensors.remove(dObj["ln"])
                                            if value is not None:
                                                row_data = evaluation.process_data(dObj, attr["p"], value,self._validation)

                                                if row_data and "RPT" in row_data:
                                                    if not attr["p"] in r_attr_s:
                                                        r_attr_s[attr["p"]] = {}
                                                    for key, value in row_data["RPT"].items():
                                                        r_attr_s[attr["p"]][key] = value

                                                if row_data and "FLT" in row_data:
                                                    if not attr["p"] in f_attr_s:
                                                        f_attr_s[attr["p"]] = {}
                                                    for key, value in row_data["FLT"].items():
                                                        f_attr_s[attr["p"]][key] = value
                                    unsensor = sensorData[attr["p"]].keys()
                                    unmatch_sensor= list((set(unsensor)- set(sub_sensors)))
                                    for unmatch in unmatch_sensor:
                                        if not attr["p"] in f_attr_s:
                                            f_attr_s[attr["p"]] = {}
                                        f_attr_s[attr["p"]][unmatch]=sensorData[attr["p"]][unmatch]
                                    data = evaluation.get_rule_data()
                                    if data is not None:
                                        rul_data.append(data)
                        unsensor=sensorData.keys()
                        unmatch_sensor= list((set(unsensor)- set(real_sensor)))
                        for unmatch in unmatch_sensor:
                            f_attr_s[unmatch]=sensorData[unmatch]
                            #--------------------------------
                        #--------------------------------
                        if self.isEdge and self.hasRules and len(rul_data) > 0:
                            for rule in self.rules:
                                rule["id"]=uniqueId
                                self._ruleEval.evalRules(rule, rul_data)
                        if len(r_attr_s.items()) > 0:
                            r_device["d"]=r_attr_s
                            rpt_data["d"].append(r_device)

                        if len(f_attr_s.items()) > 0:
                            f_device["d"]=f_attr_s
                            flt_data["d"].append(f_device)

            #--------------------------------
            #print("rtp: ",rpt_data)
            #print("flt: ",flt_data)

            if len(rpt_data["d"]) > 0:
                self.send_msg_to_broker("RPT", rpt_data)

            if len(flt_data["d"]) > 0:
                if self.isEdge:
                    if edge_flt_flag:
                        self.send_msg_to_broker("FLT", flt_data)
                else:
                    self.send_msg_to_broker("FLT", flt_data)
            #--------------------------------

        except Exception as ex:
            print(ex.message)

    def sendAckModule(self,ackGuid, status, msg):
        if self._is_process_started == False:
            return
        if not msg:
            print("sendAckModule: msg is empty.")
        if ackGuid is not None :
            pass
        else:
            raise(IoTConnectSDKException("00", "sendAckModule: ackGuid not valid."))
        try:
            template = self._Ack_data_template
            template["type"] = 2
            template["st"] = status
            template["msg"] = msg
            template["ack"] = ackGuid
            if ackGuid is not None:
                self.send_msg_to_broker("CMD_ACK", template)
        except Exception as ex:
            raise(ex)

    def sendOTAAckCmd(self,ackGuid, status, msg,childId=None):
        if self._is_process_started == False:
            return
        ischild = False
        if childId is not None and type(childId) == str:
            for d in self.devices:
                if d["id"] == childId:
                    ischild=True
        if not msg:
            print("sendAckModule: msg is empty.")
        if ackGuid is not None :
            pass
        else:
            raise(IoTConnectSDKException("00", "sendAckModule: ackGuid not valid."))
        try:
            template = self._Ack_data_template
            template["d"]["type"] = 1
            template["d"]["st"] = status
            template["d"]["msg"] = msg
            template["d"]["ack"] = ackGuid
            if ischild:
                template["d"]["cid"] = childId
                if ackGuid is not None:
                    print(template)
                    self.send_msg_to_broker("FW", template)
            elif childId:
                pass
            else:
                self.send_msg_to_broker("FW", template)
        except Exception as ex:
            raise(ex)
        
    def __create_ack_msg(self, ackGuid, status, msg, childId=None):
        if childId is not None and type(childId) == str:
            for d in self.devices:
                if d["id"] == childId:
                    ischild=True

        template = self._Ack_data_template
        template["d"]["type"] = 0
        template["d"]["st"] = status
        template["d"]["msg"] = msg
        template["d"]["ack"] = ackGuid

        if ischild:
            template["d"]["cid"] = childId
            if ackGuid is not None:
                print(template)
        elif childId:
            pass
        else:
            print(template)

    def sendAckCmd(self,ackGuid, status, msg,childId=None):
        if self._is_process_started == False:
            return
        ischild = False
        if childId is not None and type(childId) == str:
            for d in self.devices:
                if d["id"] == childId:
                    ischild=True
        if not msg:
            print("sendAckModule: msg is empty.")
        if ackGuid is not None :
            pass
        else:
            raise(IoTConnectSDKException("00", "sendAckModule: ackGuid not valid."))
        try:
            template = self._Ack_data_template
            
            template["d"]["type"] = 0
            template["d"]["st"] = status
            template["d"]["msg"] = msg
            template["d"]["ack"] = ackGuid
            print(template)
            if ischild:
                template["d"]["cid"] = childId
                if ackGuid is not None:
                    self.send_msg_to_broker("CMD_ACK", template)
            elif childId:
                pass
            else:
                self.send_msg_to_broker("CMD_ACK", template)
        except Exception as ex:
            raise(ex)

    def UpdateTwin(self, key, value):
        try:
            isvalid = True
            if self._is_process_started == False:
                self.write_debuglog('[ERR_TP02] '+ self._time +'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] Device is barred Updatetwin() method is not permitted",1)
                return
            for i in self.setting:
                if i["ln"] == key:
                    if len(i["dv"]):
                        isvalid = self.data_evaluation.twin_validate(i["dt"],i["dv"],value)
                    if isvalid:
                        _Online = False
                        _data = {}
                        _data[key] = value
                        if self._client:
                            _Online = self._client.SendTwinData(_data)
                        if _Online:
                            print("\nupdate twin data sucessfully... %s" % self._time)
        except Exception as ex:
            print(ex)

    def send_edge_data(self, data):
        try:
            if self._is_process_started == False:
                return
            template = self._data_template
            for d in self.devices:
                if (d["tg"] == data["tg"]) and (d["id"] in self._live_device):
                    if d["tg"] == "" and (not self._data_json['has']['d']):
                        device = {
                            "dt": self._timestamp,
                            "d": [],
                        }
                    else:
                        device = {
                            "id": d["id"],
                            "dt": self._timestamp,
                            "d": [],
                            "tg": d["tg"]
                        }
                    device["d"]=data["d"]
                    template["d"].append(device)
            self.send_msg_to_broker("RPTEDGE", template)
        except Exception as ex:
            print(ex)

    #need to change in 2.1 format
    def send_rule_data(self, data):
        try:
            id = data["id"]
            if self._data_json['has']['d']:
                for d in self.devices:
                    if id == d["id"]:
                        data["tg"] = d["tg"]
            tdata = {
                "dt": "",
                "d": [data],
            }
            tdata["dt"]=self._timestamp
            print(tdata)
            self.send_msg_to_broker("RMEdge", tdata)
        except Exception as ex:
            print(ex)

    def send_msg_to_broker(self, msgType, data):
        try:
            self._lock.acquire()
            #return

            _Online = False
            if self._client:
                _Online = self._client.Send(data,msgType)

            if _Online:
                if msgType == "RPTEDGE":
                    print("\nPublish edge data sucessfully... %s" % self._time)
                elif msgType == "RMEdge":
                    print("\nPublish rule matched data sucessfully... %s" % self._time)
                elif msgType == "CMD":
                    print("\nPublish Command data sucessfully... %s" % self._time)
                elif msgType == "FW":
                    print("\nPublish Firmware data sucessfully... %s" % self._time)
                elif msgType == "CMD_ACK":
                    #print (">>command acknowledge ack", data["d"]["ack"])
                    print("\nPublish command acknowledge data sucessfully... %s" % self._time)
                    self.write_debuglog('[INFO_CM10] '+'['+ str(self._sId)+'_'+str(self._uniqueId)+"] Command Acknowledgement sucessfull: "+self._time ,0)
                else:
                    print("\nPublish data sucessfully... %s" % self._time,data,msgType)

            if _Online == False:
                if self._offlineClient:
                    if self._offlineClient.Send(data):
                        self.write_debuglog('[INFO_OS02] '+'['+ str(self._sId)+'_'+str(self._uniqueId)+"] Offline data saved: "+self._time,0)
                        print("\nStoring offline sucessfully... %s" % self._time)
                    else:
                        self.write_debuglog('[ERR_OS03] '+ self._time +'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] Unable to read or write file",1)
                        print("\nYou Unable to store offline data.")

            else:
                if self._offlineClient:
                    self._offlineClient.PublishData()

            self._lock.release()
        except Exception as ex:
            print("send_msg_to_broker : ", ex)
            self._lock.release()

    def send_offline_msg_to_broker(self, data):
        _Online = False
        if self._client:
            data.update({"od":1})
            _Online = self._client.Send(data,"OD")
            if _Online:
                self.write_debuglog('[INFO_OS01] '+'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] Publish offline data: "+ self._time ,0)
        return _Online

    def command_sender(self, command_text,rule):
        try:
            if self._is_process_started == False:
                return
            template = self._command_template
            if self._data_json is not None:
                for d in self.devices:
                    if (rule['con'].find(str(d["tg"])) > -1) and (d["id"] in self._live_device):
                        template["id"] = d["id"]
                        template["command"] = command_text
                        if self._listner_device_callback is not None:
                            self._listner_device_callback(template)
        except Exception as ex:
            print(ex)

    def clear_object(self, option):
        try:
            if option == "all" or option == "attribute":
                for attr in self.attributes:
                    if "evaluation" in attr:
                        attr["evaluation"].destroyed()
                        del attr["evaluation"]
        except Exception as ex:
            raise(ex)

    def reset_process_sync_helper(self, option):
        try:
            time.sleep(1)
            self.process_sync(option)
        except Exception as ex:
            print(ex)

    def reset_process_sync(self, option):
        return threading.Thread(target = self.reset_process_sync, args = [option])

    def event_call(self, name, taget, arg):
        _thread = threading.Thread(target=getattr(self, taget), args=arg)
        #_thread.daemon = True
        _thread.setName(name)
        _thread.start()

    def delete_chield(self,child_id,callback):
        try:
            if self._is_process_started == False:
                return None
            if self._data_json["has"]["d"] != 1:
                raise(IoTConnectSDKException("00", "delete child Device not posibale. it is not gatway device. "))
            for device in self._data_json['d']:
                if child_id == device["id"]:
                    self._listner_deletechild_callback=callback
                    self.deletechild=child_id
                    template={
                        "mt": 222,
                        "d": {
                        "id": child_id
                        }}
                    if self._client:
                        self._client.send("Di",template)

        except:
            return None

    def Getdevice(self):
        try:
            if self._is_process_started == False:
                return None
            return self.devices
        except:
            return None

    def GetAttributes(self,callback):
        try:
            if callback:
                self._getattribute_callback = callback
            # self._hello_handshake({"mt":201,"sid":self._sId})
            self._hello_handshake({"mt":201})
        except Exception as ex:
            self.write_debuglog('[ERR_GA01] '+ self._time +'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] Get Attributes Error",1)
            return None

    def createChildDevice(self, deviceId, deviceTag, displayName, callback=None):
        try:
            if type(deviceId) != str and type(deviceTag) != str and type(displayName) != str:
                raise(IoTConnectSDKException("00", "Child Device deviceId|deviceTag|displayName all should be string"))

            if self._data_json["has"]["d"] != 1:
                self.write_debuglog('[ERR_GD04] '+ self._time +'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] Child device create : It is not a Gateway device",1)
                raise(IoTConnectSDKException("00", "create child Device not posibale it is not gatway device. "))
            if (type(deviceId)) != str and (" " in deviceId):
                raise(IoTConnectSDKException("00", "create child Device in deviceId space is not valid. "))
            template=self._child_template
            template["dn"]=displayName
            template["id"]=deviceId
            template["tg"]=deviceTag
            if callback:
                self._listner_creatchild_callback=callback
        except:
            self.write_debuglog('[ERR_GD01] '+ self._time +'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] Create child Device Error",1)
            raise(IoTConnectSDKException("04", "createChildDevice"))

    def __child_error_log(self,errorcode):
        error={
            "0": "OK – No Error. Child Device created successfully",
            "1": "Message missing child tag",
            "2": "Message missing child device uniqueid",
            "3": "Message missing child device display name",
            "4": "Gateway device not found",
            "5": "Could not create device, something went wrong",
            "6": "Child device tag is not valid",
            "7": "Child device tag name cannot be same as Gateway device",
            "8": "Child uniqueid is already exists.",
            "9": "Child uniqueid should not exceed 128 characters"
        }
        return error[str(errorcode)]

    @property
    def isEdge(self):
        try:
            if self._data_json is not None and "edge" in self._data_json["meta"] and self._data_json["meta"]["edge"] is not None:
                return (self._data_json["meta"]["edge"] == 1)
            else:
                return False
        except:
            return False


    @property
    def _child_template(self):
        guid=""
        if "gtw" in self._data_json["meta"] and 'g' in self._data_json["meta"]["gtw"]:
            guid=self._data_json["meta"]["gtw"]['g']
        data={
            "mt": 221,
            "d": {
                    "g": guid,
                    "dn": "",
                    "id": "",
                    "tg": ""
                }
        }
        return data
    @property
    def hasRules(self):
        try:
            key = OPTION["rule"]
            if self._data_json is not None and key in self._data_json and self._data_json[key] is not None:
                return len(self._data_json[key]) > 0
            else:
                return False
        except:
            return False

    @property
    def _timestamp(self):
        return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

    @property
    def _time(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.000")

    @property
    def _data_template(self):
        try:
            data = {
                "d": [],
                "dt": ""
            }
            data["dt"] = self._timestamp
            return data
        except:
            raise(IoTConnectSDKException("07", "telementry"))

    @property
    def _Ack_data_template(self):
        try:
            data = {
                "dt": "",
                "d": {
                    "ack": "",
                    "type": 0,
                    "st": 0,
                    "msg": "",
                }
            }
            data["dt"] = self._timestamp
            return data
        except:
            raise(IoTConnectSDKException("07", "telementry"))
    # @property
    def get_file(self):
        debug_path = os.path.join(sys.path[0], "logs")
        path_staus=os.path.exists(debug_path)
        if path_staus:
            for sub_folder in ["debug"]:
                debug_path = os.path.join(debug_path,sub_folder)
                path_staus=os.path.exists(debug_path)
                if path_staus:
                    pass
                else:
                    os.mkdir(debug_path)
        else:
            os.mkdir(debug_path)
            for sub_folder in ["debug"]:
                debug_path = os.path.join(debug_path,sub_folder)
                os.mkdir(debug_path)
        self._debug_output_path = os.path.join(debug_path,"info.txt")
        self._debug_error_path = os.path.join(debug_path,"error.txt")

    @property
    def _command_template(self):
        try:
            data = {
                "guid": "",
                "command": "",
                "ack": None,
                "ct": CMDTYPE["DCOMM"]
            }
            return data
        except:
            raise(IoTConnectSDKException("07", "command"))
        
    def get_option(self, key):
        if self._data_json is not None and key in self._data_json and self._data_json[key] is not None:
            return self._data_json[key]
        else:
            return []

    @property
    def attributes(self):
        try:
            key = OPTION["attribute"]
            return self.get_option(key)
        except:
            raise(IoTConnectSDKException("04", "attributes"))

    @property
    def devices(self):
        try:
            key = OPTION["device"]
            return self.get_option(key)
        except:
            raise(IoTConnectSDKException("04", "devices"))

    @property
    def rules(self):
        try:
            key = OPTION["rule"]
            return self.get_option(key)
        except:
            raise(IoTConnectSDKException("04", "rules"))

    @property
    def protocol(self):
        try:
            key = OPTION["protocol"]
            return self.get_option(key)
        except:
            raise(IoTConnectSDKException("04", "protocol"))

    @property
    def setting(self):
        try:
            key = OPTION["setting"]
            return self.get_option(key)
        except:
            raise(IoTConnectSDKException("04", "protocol"))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        try:
            self._is_process_started = False
            for attr in self.attributes:
                if "evaluation" in attr:
                    attr["evaluation"].destroyed()
                    del attr["evaluation"]
            if self._client and hasattr(self._client, 'Disconnect'):
                self._client.Disconnect()
        except:
            raise(IoTConnectSDKException("00", "Exit"))

    def write_debuglog(self,msg,is_error):
        if self._debug:
            if is_error:
                if self._debug_error_path:
                    with open(self._debug_error_path, "a") as dfile:
                        dfile.write(msg+'\n')
            else:
                if self._debug_output_path:
                    with open(self._debug_output_path,"a") as dfile:
                        dfile.write(msg+'\n')

    # def win_user(self):
    #     import win32api
    #     import ntplib
    #     ntp_obj = ntplib.NTPClient()
    #     time_a=datetime.utcfromtimestamp(ntp_obj.request('europe.pool.ntp.org').tx_time)
    #     win32api.SetSystemTime(time_a.year, time_a.month, time_a.weekday(), time_a.day, time_a.hour , time_a.minute, time_a.second, 0)

    def linux_user(self):
        import ctypes
        import ctypes.util
        import time
        import ntplib

        CLOCK_REALTIME = 0
        class timespc(ctypes.Structure):
            _fields_ = [("tv_sec", ctypes.c_long),("tv_nsec", ctypes.c_long)]

        librt = ctypes.CDLL(ctypes.util.find_library("rt"))
        ts = timespc()
        ntp_obj = ntplib.NTPClient()
        time_a=datetime.fromtimestamp(ntp_obj.request('pool.ntp.org').tx_time)
        time_form=[time_a.year,time_a.month,time_a.day,time_a.hour,time_a.minute,time_a.second]
        ts.tv_sec = int(time.mktime(datetime(*time_form[:6]).timetuple()))
        ts.tv_nsec=0 * 1000000
        librt.clock_settime(CLOCK_REALTIME,ctypes.byref(ts))

    def __init__(self, uniqueId, sId,sdkOptions=None,initCallback=None):
        self._lock = threading.Lock()

#        if sys.platform == 'win32':
#            self.win_user()
#        elif sys.platform == 'linux2':
#            self.linux_user()

        #ByPass SSL Verification
        if (not os.environ.get('PYTHONHTTPSVERIFY', '') and getattr(ssl, '_create_unverified_context', None)):
            ssl._create_default_https_context = ssl._create_unverified_context

        if sdkOptions == None:
            self._property = {
            	"certificate" : None,
                "offlineStorage":
                    {
                    "disabled":False,
	                "availSpaceInMb": None,
	                "fileCount": 1
                    },
                "IsDebug":False,
                "keepalive":60
                }
        else:
            self._property = sdkOptions

        if initCallback:
            self._listner_callback=initCallback

        self._get_config()
        if self._debug:
            self.get_file()
        if not sId:
            self.write_debuglog('[ERR_IN04] '+ self._time +'['+ str(sId)+'_'+ str(uniqueId)+']:'+'SId can not be blank',1)
            raise ValueError("SId must contain a value.")

        if not uniqueId:
            raise ValueError("Unique ID must contain a value.")

        if self._config == None:
            raise(IoTConnectSDKException("01", "Config settings"))

        self._sId = sId
        self._uniqueId = uniqueId
        if "discoveryUrl" in self._property:
            if "http" not in self._property["discoveryUrl"] :
                self.write_debuglog('[ERR_IN02] '+ self._time +'['+ str(sId)+'_'+ str(uniqueId)+ "] Discovery URL can not be blank",1)
                raise(IoTConnectSDKException("01", "discoveryUrl"))
            else:
                pass
        else:
            self._property["discoveryUrl"]="https://discovery.iotconnect.io"

        if ("offlineStorage" in self._property) and ("disabled" in self._property["offlineStorage"]) and ("availSpaceInMb" in self._property["offlineStorage"]) and ("fileCount" in self._property["offlineStorage"]) :
            if  self._property["offlineStorage"]["disabled"] == False:
                self._offlineClient = offlineclient(sId+'_'+uniqueId,self._config, self.send_offline_msg_to_broker)
                self.write_debuglog('[INFO_OS03] '+'['+ str(sId)+'_'+str(uniqueId)+"] File has been created to store offline data: "+self._time,0)
        else:
            print("offline storage is disabled...")

        if ("skipValidation" in self._property):
            if self._property["skipValidation"]:
                self._validation=False

        self._ruleEval = rule_evaluation(self.send_rule_data, self.command_sender)

        self._identity_base_url, self._pf = self.__discover(self._property['discoveryUrl'], self._sId)
        if self._identity_base_url is not None:
            self.write_debuglog('[INFO_IN07] '+'['+ str(self._sId)+'_'+ str(self._uniqueId) + "] BaseUrl received to sync the device information: "+ self._time ,0)
            self.process_sync("all")
            try:
                while self._is_process_started == False:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                sys.exit(0)
        else:
            msg = f"Network connection error or invalid url: {self._base_url}"
            self.write_debuglog(msg,1)
            raise(IoTConnectSDKException("02", msg))
