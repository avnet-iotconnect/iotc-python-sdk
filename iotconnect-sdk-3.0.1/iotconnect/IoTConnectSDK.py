import sys
import json
import os.path
import copy
import time
import threading
import ssl

from datetime import datetime
from threading import Timer
if ('linux' in sys.platform) and (sys.version_info >=(3,5)):
    import jsonlib
if sys.version_info >= (3, 5):
    import http.client as httplib
    import urllib.request as urllib
    from urllib.parse import urlparse
else:
    import httplib
    import urllib2 as urllib
    from urlparse import urlparse

from provisioning_device_client import *

from iotconnect.client.mqttclient import mqttclient
from iotconnect.client.httpclient import httpclient
from iotconnect.client.dpsclient import dpsclient
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
RCCode = {
    "OK": 0,
    "DEV_NOT_REG": 1,
    "AUTO_REG": 2,
    "DEV_NOT_FOUND": 3,
    "DEV_INACTIVE": 4,
    "OBJ_MOVED": 5,
    "CPID_NOT_FOUND": 6
}
CMDTYPE = {
    "DCOMM": "0x01",
    "FIRMWARE": "0x02",
    "U_ATTRIBUTE": "0x10",
    "U_SETTING": "0x11",
    "U_PROTOCOL": "0x12",
    "U_DEVICE": "0x13",
    "U_RULE": "0x15",
    "U_barred":"0x99",
    "is_connect": "0x16",
    "SYNC": "sync",
    "RESETPWD": "resetpwd",
    "UCART": "updatecrt",
}
OPTION = {
    "attribute": "att",
    "setting": "s",
    "protocol": "p",
    "device": "d",
    "sdkConfig": "sc",
    "rule": "r"
}

DATATYPE = {
    0:"NUMBER",
    1:"STRING",
    2:"OBJECT",
    3:"FLOAT" 
}

class IoTConnectSDK:
    _property=None
    _config = None
    _cpId = None
    _uniqueId = None
    _listner_callback = None
    _listner_twin_callback = None
    _data_json = None
    _client = None
    _is_process_started = False
    _base_url = ""
    _thread = None
    _ruleEval = None
    _offlineClient = None
    _lock = None
    _reg_result = None
    _iot_hub_url = None
    _registration_id  = None
    _auth_type=None
    _dispose = False
    _live_device=[]
    _debug=False
    _data_freqency = 60
    _dftime=None
    _debug_output_path=None
    _debug_error_path=None

    def get_config(self):
        try:
            self._config = None
            _path = os.path.abspath(os.path.dirname(__file__))
            _config_path = os.path.join(_path, "assets/config.json")
            with open(_config_path) as config_file:
                self._config = json.loads(config_file.read())
            self.get_properties()
        except:
            raise(IoTConnectSDKException("01", "Config file"))
    """
    #only in standard lib
    def GetAllTwins(self):
        if self._dispose == True:
            raise(IoTConnectSDKException("00", "you are not able to call this function"))
        if self._is_process_started == False:
            return
        if self._client:
            self._client.get_twin() 
    """

    def get_properties(self):
        try:
            _properties = self._property
            if _properties != None:
                for prop in _properties:
                    if _properties[prop]:
                        self._config[prop] = _properties[prop]
                    else:
                        self._config[prop] = None
                    if prop == 'IsDebug' and _properties[prop] == True:
                        self._debug=True
        except Exception as ex:
            raise(ex)
    
    def get_base_url(self, cpId):
        try:
            base_url = "/api/sdk/cpid/{cpid}/lang/{sdk_lang}/ver/{sdk_version}/env/{env}"
            base_url = self._property["discoveryUrl"] + base_url
            base_url = base_url.replace("{cpid}", cpId)
            base_url = base_url.replace("{sdk_lang}", self._config["sdk_lang"])
            base_url = base_url.replace("{sdk_version}", self._config["sdk_version"])
            base_url = base_url.replace("{env}", self._config["env"])
            res = urllib.urlopen(base_url).read()
            if ('linux' in sys.platform) and (sys.version_info >=(3,5)):
                data=jsonlib.read(res)
            else:
                data = json.loads(res)
            return data["baseUrl"]
        except:
            return None
    
    def post_call(self, url, body):
        try:
            parsed_uri = urlparse(url)
            scheme = parsed_uri.scheme
            host = parsed_uri.hostname
            port = parsed_uri.port
            path = parsed_uri.path
            if port == None:
                if scheme == "http":
                    conn = httplib.HTTPConnection(host)
                else:
                    conn = httplib.HTTPSConnection(host)
            else:
                if scheme == "http":
                    conn = httplib.HTTPConnection(host, port)
                else:
                    conn = httplib.HTTPSConnection(host, port)
            conn.request("POST", path, body, { "Content-type": "application/json", "Accept": "application/json"})
            response = conn.getresponse()
            res=response.read()
            if ('linux' in sys.platform) and (sys.version_info >=(3,5)):
                data=jsonlib.read(res)
            else:
                data=json.loads(res)
            conn.close()
            return data
        except:
            return None

    def Dispose(self):
        try:
            if self._dispose == True:
                self.write_debuglog('[ERR_DC02] '+ self._time +'['+ str(self._cpId)+'_'+ str(self._uniqueId) + "] Connection not available",1)
                self.write_debuglog('[INFO_DC01] '+'['+ str(self._cpId)+'_'+str(self._uniqueId)+"] Device already disconnected: "+self._time,0)
                return True
            for attr in self.attributes:
                if self.has_key(attr, "evaluation"):
                    attr["evaluation"].destroyed()
                    del attr["evaluation"]
            if self._client and hasattr(self._client, 'Disconnect'):
                self._client.Disconnect()
            self._is_process_started=False
            self._dispose = True
            self._property=None
            self._config = None
            self._cpId = None
            self._uniqueId = None
            self._listner_callback = None
            self._listner_twin_callback = None
            self._data_json = None
            self._client = None
            self._base_url = ""
            self._thread = None
            self._ruleEval = None
            self._offlineClient = None
            self._lock = None
            self._live_device=[]
            self._debug=False
            return True
        except:
            raise(IoTConnectSDKException("00","Dispose error.."))
        
    def onMessage(self, msg):
        try:
            if self._dispose == True:
                return
            if msg == None:
                return
            msg = msg

            if "cmdType" in msg:
                if msg["cmdType"] == CMDTYPE["is_connect"]:
                    msg["data"]["cpId"] = self._cpId
                    msg["data"]["uniqueId"] = self._uniqueId
                    if self._listner_callback:
                        self._listner_callback(msg["data"])
                    self.write_debuglog('[INFO_CM09] '+ self._time +'['+ str(self._cpId)+'_'+ str(self._uniqueId) + "] 0x16 sdk connection status: " + msg["data"]["command"],0)
                    return

            if self._is_process_started == False:
                return        
            if "cmdType" not in msg:
                print("Invalid Message : " + json.dumps(msg))
                return

            _tProcess = None
            if msg["cmdType"] == CMDTYPE["U_ATTRIBUTE"]:
                _tProcess = threading.Thread(target = self.reset_process_sync, args = ["attribute"])
            elif msg["cmdType"] == CMDTYPE["U_SETTING"]:
                _tProcess = threading.Thread(target = self.reset_process_sync, args = ["setting"])
            elif msg["cmdType"] == CMDTYPE["U_PROTOCOL"]:
                _tProcess = threading.Thread(target = self.reset_process_sync, args = ["protocol"])
            elif msg["cmdType"] == CMDTYPE["U_DEVICE"]:
                _tProcess = threading.Thread(target = self.reset_process_sync, args = ["device"])
            elif msg["cmdType"] == CMDTYPE["U_RULE"]:
                _tProcess = threading.Thread(target = self.reset_process_sync, args = ["rule"])
            elif msg["cmdType"] == CMDTYPE["SYNC"]:
                _tProcess = threading.Thread(target = self.reset_process_sync, args = ["all"])
            elif msg["cmdType"] == CMDTYPE["RESETPWD"]:
                _tProcess = threading.Thread(target = self.reset_process_sync, args = ["protocol"])
            elif msg["cmdType"] == CMDTYPE["UCART"]:
                pass
            elif msg["cmdType"] == CMDTYPE["DCOMM"] or msg["cmdType"] == CMDTYPE["FIRMWARE"]:
                if self._listner_callback != None:
                    self._listner_callback(msg["data"])
            elif msg["cmdType"] == CMDTYPE["U_barred"]:
                self._is_process_started=False
                if  self._offlineClient:
                    self._offlineClient.clear_all_files()
                if self._client and hasattr(self._client, 'Disconnect'):
                    self._client.Disconnect()
                print("0x99 command received so device is barred")
                #_tProcess = threading.Thread(target = self.reset_process_sync, args = ["all"])
            else:
                print("Message : " + json.dumps(msg))
            
            if _tProcess != None:
                _tProcess.setName("PSYNC")
                _tProcess.daemon = True
                _tProcess.start()
        except  Exception as ex:
            print("Message process failed..."+ str(ex))
    
    def onTwinMessage(self, msg):
        try:
            if self._dispose == True:
                raise(IoTConnectSDKException("00", "you are not able to call this function"))    
            if self._is_process_started == False:
                return
            if msg == None:
                return
            msg = json.loads(msg)
            msg["uniqueId"] = self._uniqueId
            if len(msg.items()) == 0:
                return
            if self._listner_twin_callback != None:
                self._listner_twin_callback(msg)
        except Exception as ex:
            print("Message process failed..." + str(ex))
    
    def init_protocol(self):
        try:
            protocol_cofig = self.protocol
            name = protocol_cofig["n"]
            self._auth_type=self._data_json['at']
            auth_type = self._data_json['at']
            
            if self._client != None:
                self._client = None
            
            if name == "mqtt" and auth_type != 4:
                self._client = mqttclient(auth_type, protocol_cofig, self._config, self.onMessage, self.onTwinMessage) 
            elif name == "mqtt" and auth_type == 4:
                self._client = dpsclient(auth_type, protocol_cofig, self._config, self.onMessage,self.onTwinMessage)
            elif name == "http" or name == "https":
                self._client = httpclient(protocol_cofig, self._config)
            else:
                self._client = None
        except Exception as ex:
            raise(ex)
    
    def init_provisioning_client(self):
        try:
            is_registered = False
            provisioning_client = None
            def register_device_callback(reg_result, iothub_uri, device_id, user_context):
                self._reg_result = reg_result
                self._iot_hub_url = iothub_uri
                self._registration_id = device_id
            
            def register_status_callback(reg_status, user_context):
                pass
            
            try:
                provisioning_client = ProvisioningDeviceClient(self._global_prov_url, self._scope_id, ProvisioningSecurityDeviceType.TPM, ProvisioningTransportProvider.HTTP)
                provisioning_client.set_option("registration_id", self._registration_id)
                provisioning_client.register_device(register_device_callback, None, register_status_callback, None)
            except Exception as ex:
                register_result = ProvisioningDeviceResult.ERROR
            
            while self._reg_result == None:
                time.sleep(0.5)
            
            provisioning_client = None
            if self._reg_result == ProvisioningDeviceResult.OK and self._iot_hub_url != None and self._registration_id != None:
                is_registered = True
            
            return is_registered
        except Exception as ex:
            #raise(ex)
            return False
    
    def process_sync(self, option):
        try:   
            url = self._base_url
            req_json = {}
            req_json["uniqueId"] = self._uniqueId
            req_json["cpId"] = self._cpId
            req_json["option"] = { }
            if option == "all":
                req_json["option"]["attribute"] = True
                req_json["option"]["setting"] = True
                req_json["option"]["protocol"] = True
                req_json["option"]["device"] = True
                req_json["option"]["sdkConfig"] = True
                req_json["option"]["rule"] = True
            else:
                req_json["option"][option] = True
            
            body = json.dumps(req_json)
            response = self.post_call(url + 'sync', body)
            
            isReChecking = False
            if option == "all":
                if response == None:
                    raise(IoTConnectSDKException("01", "Sync response"))
                elif response != None and self.has_key(response, "status"):
                    raise(IoTConnectSDKException("03", response["message"]))
                else:
                    response = response["d"]
                    #print response
                    if response["at"] == 4:
                        if response["ds"] == RCCode["DEV_NOT_REG"]:
                            is_registered = self.init_provisioning_client()
                            if is_registered == True:
                                print("\nDevice registered successfully!")
                            isReChecking = True
                    else:
                        if response["rc"] != RCCode["OK"]:
                            isReChecking = True
            else:
                if response == None:
                    isReChecking = True
                elif response != None and self.has_key(response, "status"):
                    isReChecking = True
                else:
                    response = response["d"]
                    if response["rc"] != RCCode["OK"]:
                        isReChecking = True
            
            if isReChecking:
                print("\nRe-Checking...")
                _tProcess = threading.Thread(target = self.reset_process_sync, args = [option])
                _tProcess.setName("PSYNC")
                _tProcess.daemon = True
                _tProcess.start()
                return
            else:
                self._is_process_started = False
                # Pre Process
                self.clear_object(option)
                #print(json.dumps(response))
                # --------------------------------
                if option == "all":
                    self._data_json = response
                else:
                    key = OPTION[option]
                    if self._data_json and self.has_key(self._data_json, key):
                        self._data_json[key] = response[key]
                    print("\n" + option + " updated sucessfully...")
                
                if option == "all" or option == "attribute":
                    for attr in self.attributes:
                        attr["evaluation"] = data_evaluation(self.isEdge, attr, self.send_edge_data)
                
                if option == "all" or option == "protocol":
                    self.init_protocol()

                if "df" in self._data_json['sc']:
                    self._data_freqency=self._data_json['sc']["df"]
                self._is_process_started = True
        except Exception as ex:
            raise(ex)
    
    def find_df(self,seconds): 
        seconds = seconds % (24 * 3600) 
        hour = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        return int("%02d%02d%02d" % (hour, minutes, seconds))

    def SendData(self,jsonArray):
        try:
            if self._dispose == True:
                raise(IoTConnectSDKException("00", "you are not able to call this function"))
            if self._is_process_started == False:
                self.write_debuglog('[ERR_SD04] '+ self._time +'['+ str(self._cpId)+'_'+ str(self._uniqueId) + "] Device is barred SendData() method is not permitted",1)
                return
            
            nowtime=int(datetime.now().strftime("%Y%m%d%H%M%S"))
            if not self.isEdge:
                if self._dftime != None:
                    if nowtime >= self._dftime:
                        self._dftime = nowtime + self.find_df(self._data_freqency)
                    else:
                        return
                else:
                    self._dftime = nowtime + self.find_df(self._data_freqency)
            
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
                    if self.has_key(attr, "evaluation"):
                        evaluation = attr["evaluation"]
                        evaluation.reset_get_rule_data()
                for d in self.devices:
                    if d["id"] == uniqueId:
                        if uniqueId not in self._live_device:
                            self._live_device.append(uniqueId)
                        tg = d["tg"]
                        r_device = {
                            "id": uniqueId,
                            "dt": time,
                            "d": [],
                            "tg": d["tg"]
                        }
                        f_device = copy.deepcopy(r_device)
                        r_attr_s = {}
                        f_attr_s = {}
                        for attr in self.attributes:
                            if attr["p"] == "" and attr["tg"] == "" and self.has_key(attr, "evaluation"):
                                evaluation = attr["evaluation"]
                                evaluation.reset_get_rule_data()
                                for dObj in attr["d"]:
                                    if tg == dObj["tg"] and self.has_key(sensorData, dObj["ln"]):
                                        value = sensorData[dObj["ln"]]
                                        row_data = evaluation.process_data(dObj, attr["p"], value)
                                        if row_data and self.has_key(row_data, "RPT"):
                                            for key, value in row_data["RPT"].items():
                                                r_attr_s[key] = value
                                        if row_data and self.has_key(row_data, "FLT"):
                                            for key, value in row_data["FLT"].items():
                                                f_attr_s[key] = value
                                
                                data = evaluation.get_rule_data()
                                #print "rule data: ",data
                                if data != None:
                                    rul_data.append(data)
                            
                            elif attr["p"] != "" and tg == attr["tg"] and self.has_key(attr, "evaluation") and self.has_key(sensorData, attr["p"]) == True:
                                evaluation = attr["evaluation"]
                                evaluation.reset_get_rule_data()
                                for dObj in attr["d"]:
                                    if self.has_key(sensorData[attr["p"]], dObj["ln"]):
                                        value = sensorData[attr["p"]][dObj["ln"]]
                                        row_data = evaluation.process_data(dObj, attr["p"], value)
                                        if row_data and self.has_key(row_data, "RPT"):
                                            if self.has_key(r_attr_s, attr["p"]) == False:
                                                r_attr_s[attr["p"]] = {}
                                            for key, value in row_data["RPT"].items():
                                                r_attr_s[attr["p"]][key] = value
                                            
                                        if row_data and self.has_key(row_data, "FLT"):
                                            if self.has_key(f_attr_s, attr["p"]) == False:
                                                f_attr_s[attr["p"]] = {}
                                            for key, value in row_data["FLT"].items():
                                                f_attr_s[attr["p"]][key] = value
                                data = evaluation.get_rule_data()
                                #print "rule data: ",data
                                if data != None:
                                    rul_data.append(data)
                            #--------------------------------
                        #--------------------------------
                        if self.isEdge and self.hasRules and len(rul_data) > 0:
                            for rule in self.rules:
                                self._ruleEval.evalRules(rule, rul_data)
                        if len(r_attr_s.items()) > 0:
                            r_device["d"].append(r_attr_s)
                            rpt_data["d"].append(r_device)
                        
                        if len(f_attr_s.items()) > 0:
                            f_device["d"].append(f_attr_s)
                            flt_data["d"].append(f_device)        
            
            #--------------------------------
            if len(rpt_data["d"]) > 0:
                rpt_data["mt"] = MSGTYPE["RPT"]
                self.send_msg_to_broker("RPT", rpt_data)

            if len(flt_data["d"]) > 0:
                flt_data["mt"] = MSGTYPE["FLT"]
                self.send_msg_to_broker("FLT", flt_data)
            #--------------------------------
            
        except Exception as ex:
            if self._dispose == False:
                print(ex)
            else:
                print(ex.message)
    
    def SendAck(self,data,msgType):
        if self._dispose == True:
            raise(IoTConnectSDKException("00", "you are not able to call this function"))
        if self._is_process_started == False:
            return
        if not data:
            raise(IoTConnectSDKException("00", "SendACK: data is empty."))
        if msgType == 11 or msgType == 5:
            pass
        else:
            raise(IoTConnectSDKException("00", "SendACK: msgType not valid."))
        try:
            template = self._Ack_data_template
            template["mt"] = msgType
            template["d"] = data
            if msgType == 11:
                self.send_msg_to_broker("FW", template)
            elif msgType == 5:
                self.send_msg_to_broker("CMD_ACK", template)    
        except Exception as ex:
            raise(ex)
    
    def UpdateTwin(self, key, value):
        try:
            if self._dispose == True:
                raise(IoTConnectSDKException("00", "you are not able to call this function"))
            if self._is_process_started == False:
                self.write_debuglog('[ERR_TP02] '+ self._time +'['+ str(self._cpId)+'_'+ str(self._uniqueId) + "] Device is barred Updatetwin() method is not permitted",1)
                return
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
            if self._dispose == True:
                return
            if self._is_process_started == False:
                return
            template = self._data_template
            template["mt"] = MSGTYPE["RPTEDGE"]
            for d in self.devices:
                if (d["tg"] == data["tg"]) and (d["id"] in self._live_device):
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
    
    def send_rule_data(self, data, rule):
        try:
            tdata = {
                "dtg": "",
                "d": [],
                "cpId": "",
                "t": self._timestamp,
                "mt": "",
                "sdk": {
                    "l": self._config["sdk_lang"],
                    "v": self._config["sdk_version"],
                    "e": self._config["env"]
                }
            }
            template = tdata
            template["mt"] = MSGTYPE["RMEdge"]
            template["cpId"] = self._data_json["cpId"]
            template["dtg"] = self._data_json["dtg"]
            for d in self.devices:
                if (rule['con'].find(str(d["tg"])) > -1) and (d["id"] in self._live_device):
                    device = {
                        "id": d["id"],
                        "dt": self._timestamp,                    
                        "cv": data[0],
                        "d": [data[1]],
                        "rg": rule["g"],
                        "ct": rule["con"],
                        "sg": rule["es"]
                    }
                    template["d"].append(device)
            
            self.send_msg_to_broker("RMEdge", template)
        except Exception as ex:
            print(ex)
    
    def send_msg_to_broker(self, msgType, data):
        try:
            self._lock.acquire()
            #print(json.dumps(data))
            #return
            _Online = False
            if self._client:
                _Online = self._client.Send(data)
            #_Online=False
            if _Online:
                if msgType == "RPTEDGE":
                    print("\nPublish edge data sucessfully... %s" % self._time)
                elif msgType == "RMEdge":
                    print("\nPublish rule matched data sucessfully... %s" % self._time)
                elif msgType == "CMD_ACK":
                    print("\nPublish Command data sucessfully... %s" % self._time)
                elif msgType == "FW":
                    print("\nPublish Firmware data sucessfully... %s" % self._time)
                else:
                    print("\nPublish data sucessfully... %s" % self._time)
            
            if _Online == False:
                if self._offlineClient:
                    if self._offlineClient.Send(data):
                        self.write_debuglog('[INFO_OS02] '+'['+ str(self._cpId)+'_'+str(self._uniqueId)+"] Offline data saved: "+self._time,0)
                        print("\nStoring offline sucessfully... %s" % self._time)
                    else:
                        self.write_debuglog('[ERR_OS03] '+ self._time +'['+ str(self._cpId)+'_'+ str(self._uniqueId) + "] Unable to read or write file",1)
                        print("\nYou don't have permission to access 'offlineData.txt'.")
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
            _Online = self._client.Send(data)
            if _Online:
                self.write_debuglog('[INFO_OS01] '+'['+ str(self._cpId)+'_'+ str(self._uniqueId) + "] Publish offline data: "+ self._time ,0)
        return _Online
    
    def command_sender(self, command_text,rule):
        try:
            template = self._command_template
            if self._data_json != None:
                template["cpId"] = self._data_json["cpId"]
                for d in self.devices:
                    if (rule['con'].find(str(d["tg"])) > -1) and (d["id"] in self._live_device):
                        template["guid"] = ""
                        template["uniqueId"] = d["id"]
                        template["command"] = command_text
                        if self._listner_callback != None:
                            self._listner_callback(template)
        except Exception as ex:
            raise(ex)
        
    def clear_object(self, option):
        try:
            if option == "all" or option == "attribute":
                for attr in self.attributes:
                    if self.has_key(attr, "evaluation"):
                        attr["evaluation"].destroyed()
                        del attr["evaluation"]
        except Exception as ex:
            raise(ex)

    def reset_process_sync(self, option):
        try:
            time.sleep(1)
            self.process_sync(option)
        except Exception as ex:
            raise(ex)
    
    def event_call(self, name, taget, arg):
        _thread = threading.Thread(target=getattr(self, taget), args=arg)
        _thread.daemon = True
        _thread.setName(name)
        _thread.start()
    
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
        self._debug_output_path = os.path.join(debug_path,"Output.txt")
        self._debug_error_path = os.path.join(debug_path,"error.txt")    

    def GetAttributes(self):
        try:
            if self._dispose == True:
                raise(IoTConnectSDKException("00", "you are not able to call this function"))

            if self._is_process_started == False:
                return None
            tgs = []
            data = []
            for dObj in self.devices:
                tg = dObj["tg"]
                if str(tg) in tgs:
                    continue
                
                if len(tg):
                    dtObj = {
                        "device":{
                            "id": dObj["id"],
                            "tg" : str(tg)
                            },
                        "attributes": [],
                    }
                else:
                    dtObj = {
                        "device":{
                            "id": dObj["id"]
                            },
                        "attributes": [],
                    }
                for aObj in self.attributes:
                    if aObj["p"] == "" and aObj["tg"] =="":
                        ptObj={}
                        for pObj in aObj["d"]:
                            if tg == pObj["tg"]:
                                if "tw" in pObj:
                                    ptObj = {
                                    "ln": pObj["ln"],
                                    "dt": DATATYPE[pObj["dt"]],
                                    "dv": pObj["dv"]
                                    } 
                                else:   
                                    ptObj = {
                                        "ln": pObj["ln"],
                                        "dt": DATATYPE[pObj["dt"]],
                                        "dv": pObj["dv"],
                                    }
                                #atObj["d"].append(ptObj)
                            if len(ptObj) > 0:
                                dtObj["attributes"].append(ptObj)
                                ptObj={}
                    else:
                        if aObj["p"] != "" and tg == aObj["tg"]:
                            if aObj["tg"] == "":
                                atObj = {
                                    "ln": aObj["p"],
                                    "dt": DATATYPE[aObj["dt"]],
                                    "d": []
                                    }
                            else:
                                atObj = {
                                    "ln": aObj["p"],
                                    "dt": DATATYPE[aObj["dt"]],
                                    "tg": pObj["tg"],
                                    "d": []
                                    }
                            ptObj={}
                            for pObj in aObj["d"]:
                                if "tw" in pObj:
                                    if pObj["tg"] == '':
                                        ptObj = {
                                            "ln": pObj["ln"],
                                            "dt": DATATYPE[pObj["dt"]],
                                            "dv": pObj["dv"],
                                        }
                                    else:
                                        ptObj = {
                                            "ln": pObj["ln"],
                                            "dt": DATATYPE[pObj["dt"]],
                                            "dv": pObj["dv"],
                                            "tg": pObj["tg"]
                                        }
                                else:
                                    if pObj["tg"] == '':
                                        ptObj = {
                                            "ln": pObj["ln"],
                                            "dt": DATATYPE[pObj["dt"]],
                                            "dv": pObj["dv"],
                                        }
                                    else:
                                        ptObj = {
                                            "ln": pObj["ln"],
                                            "dt": DATATYPE[pObj["dt"]],
                                            "dv": pObj["dv"],
                                            "tg": pObj["tg"]
                                        }
                                atObj["d"].append(ptObj)
                            if len(atObj["d"]) > 0:
                                dtObj["attributes"].append(atObj)
                if len(dtObj["attributes"]) > 0:
                    data.append(dtObj)
                tgs.append(tg)
            return data
        except Exception as ex:
            raise ex
    
    def has_key(self, data, key):
        try:
            return key in data
        except:
            return False
    
    def is_not_blank(self, s):
        return bool(s and s.strip())
    
    @property
    def isEdge(self):
        try:
            if self._data_json != None and self.has_key(self._data_json, "ee") and self._data_json["ee"] != None:
                return (self._data_json["ee"] == 1)
            else:
                return False
        except:
            return False
    
    @property
    def hasRules(self):
        try:
            key = OPTION["rule"]
            if self._data_json != None and self.has_key(self._data_json, key) and self._data_json[key] != None:
                return len(self._data_json[key]) > 0
            else:
                return False
        except:
            return False
    
    @property
    def _timestamp(self):
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    @property
    def _time(self):
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    @property
    def _data_template(self):
        try:
            data = {
                "cpId": "",
                "t": "",
                "mt": "",
                "d": [],
                "dtg" : "",
                "sdk": {
                    "l": self._config["sdk_lang"],
                    "v": self._config["sdk_version"],
                    "e": self._config["env"]
                }
            }
            data["t"] = self._timestamp
            if self._data_json != None:
                data["cpId"] = self._data_json["cpId"]
                data["dtg"] = self._data_json["dtg"]
            return data
        except:
            raise(IoTConnectSDKException("07", "telementry"))
    
    @property
    def _Ack_data_template(self):
        try:
            data = {
                "cpId": "",
                "uniqueId": "",
                "t": "",
                "mt": "",
                "d": [],
                "sdk": {
                    "l": self._config["sdk_lang"],
                    "v": self._config["sdk_version"],
                    "e": self._config["env"]
                }
            }
            data["t"] = self._timestamp
            if self._data_json != None:
                data["cpId"] = self._data_json["cpId"]
                data["uniqueId"] = self._data_json["d"][0]['id']
            return data
        except:
            raise(IoTConnectSDKException("07", "telementry"))

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
        self._debug_output_path = os.path.join(debug_path,"Output.txt")
        self._debug_error_path = os.path.join(debug_path,"error.txt")

    @property
    def _command_template(self):
        try:
            data = {
                "cpId": "",
                "guid": "",
                "uniqueId": "",
                "command": "",
                "ack" : True,
                "ackId": None,
                "cmdType": CMDTYPE["DCOMM"]
            }
            if self._data_json != None:
                data["cpId"] = self._data_json["cpId"]
                for d in self.devices:
                    data["guid"] = ""
                    data["uniqueId"] = d["id"]
            return data
        except:
            raise(IoTConnectSDKException("07", "command"))
    
    @property
    def attributes(self):
        try:
            key = OPTION["attribute"]
            if self._data_json != None and self.has_key(self._data_json, key) and self._data_json[key] != None:
                return self._data_json[key]
            else:
                return []
        except:
            raise(IoTConnectSDKException("04", "attributes"))
    
    @property
    def devices(self):
        try:
            key = OPTION["device"]
            if self._data_json != None and self.has_key(self._data_json, key) and self._data_json[key] != None:
                return self._data_json[key]
            else:
                return []
        except:
            raise(IoTConnectSDKException("04", "devices"))
    
    @property
    def rules(self):
        try:
            key = OPTION["rule"]
            if self._data_json != None and self.has_key(self._data_json, key) and self._data_json[key] != None:
                return self._data_json[key]
            else:
                return []
        except:
            raise(IoTConnectSDKException("04", "rules"))
    
    @property
    def protocol(self):
        try:
            key = OPTION["protocol"]
            if self._data_json != None and self.has_key(self._data_json, key) and self._data_json[key] != None:
                return self._data_json[key]
            else:
                return None
        except:
            raise(IoTConnectSDKException("04", "protocol"))
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, exc_tb):
        try:
            for attr in self.attributes:
                if self.has_key(attr, "evaluation"):
                    attr["evaluation"].destroyed()
                    del attr["evaluation"]
            if self._client and hasattr(self._client, 'Disconnect'):
                self._client.Disconnect()
        except:
            raise(IoTConnectSDKException("00", "Exit"))

    def win_user(self):
        import win32api
        import ntplib
        conn_ntp=1
        while conn_ntp:
            try:
                conn_ntp=conn_ntp+1
                ntp_obj = ntplib.NTPClient()
                time_a=datetime.utcfromtimestamp(ntp_obj.request('europe.pool.ntp.org').tx_time)
                win32api.SetSystemTime(time_a.year, time_a.month, time_a.weekday(), time_a.day, time_a.hour , time_a.minute, time_a.second, 0)
                conn_ntp=0
            except:
                if conn_ntp == 5:
                    conn_ntp = 0
                pass

    def linux_user(self):
        import ctypes
        import ctypes.util
        import time
        import ntplib
        conn_ntp=1
        while conn_ntp:
            try:
                conn_ntp=conn_ntp+1
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
                conn_ntp = 0
            except:
                if conn_ntp == 5:
                    conn_ntp = 0
                pass

    def __init__(self, cpId, uniqueId, scopeId, listner, listner_twin,sdkOptions=None, env="PROD"):
        self._lock = threading.Lock()
            
        if sys.platform == 'win32':
            self.win_user()
        elif sys.platform == 'linux2':
            self.linux_user()
        #ByPass SSL Verification
        if (not os.environ.get('PYTHONHTTPSVERIFY', '') and getattr(ssl, '_create_unverified_context', None)):
            ssl._create_default_https_context = ssl._create_unverified_context

        if sdkOptions == None:
            self._property = {
            	"certificate" : None,
                "offlineStorage":
                    {
                    "disabled":False,
	                "maxSize": None,
	                "fileCount": 1
                    },
                "IsDebug":False,
                "discoveryUrl" : "https://discovery.iotconnect.io"   #mandatory parameter
                }
        else:
            self._property = sdkOptions
        self.get_config()
        if self._debug:
            self.get_file()

        if not self.is_not_blank(cpId):
            self.write_debuglog('[ERR_IN04] '+ self._time +'['+ cpId+'_'+ uniqueId+']:'+'cpId can not be blank',1)
            raise(IoTConnectSDKException("01", "CPID"))
        if not self.is_not_blank(uniqueId):
            self.write_debuglog('[ERR_IN05] '+ self._time +'['+ cpId+'_'+ uniqueId+']:'+'uniqueId can not be blank',1)
            raise(IoTConnectSDKException("01", "Unique Id"))
        if not self.is_not_blank(scopeId):
            raise(IoTConnectSDKException("01", "Scope Id"))
        if self._config == None:
            raise(IoTConnectSDKException("01", "Config settings"))

        self._cpId = cpId
        self._uniqueId = uniqueId
        self._scope_id = scopeId
        self._registration_id = str(cpId + "-" + uniqueId)
        self._global_prov_url = str(self._config["api_global_prov_url"])
        self._iot_hub_url = None
        self._reg_result = None

        self._config["env"] = env
        if self._debug:
            self.get_file()

        if "discoveryUrl" in self._property:
            if "http" not in self._property["discoveryUrl"] :
                self.write_debuglog('[ERR_IN02] '+ self._time +'['+ str(cpId)+'_'+ str(uniqueId)+ "] Discovery URL can not be blank",1)
                raise(IoTConnectSDKException("01", "discoveryUrl"))
        else:
            self._property["discoveryUrl"]="https://discovery.iotconnect.io"

        if "disabled" in self._property["offlineStorage"]:
            if  ("disabled" in self._property["offlineStorage"]) and (self._property["offlineStorage"]["disabled"] == False):
                self._offlineClient = offlineclient(cpId+'_'+uniqueId,self._config, self.send_offline_msg_to_broker)
                self.write_debuglog('[INFO_OS03] '+'['+ str(cpId)+'_'+str(uniqueId)+"] File has been created to store offline data: "+self._time,0)
        else:
            print("offline storage is disabled...")
        
        self._ruleEval = rule_evaluation(self.send_rule_data, self.command_sender)
        
        if listner != None:
            self._listner_callback = listner
        
        if listner_twin != None:
            self._listner_twin_callback = listner_twin
        
        self._base_url = self.get_base_url(self._cpId)
        if self._base_url != None:
            self.process_sync("all")
            try:
                while self._is_process_started == False:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                sys.exit(0)
        else:
            self.write_debuglog('[ERR_IN08] '+ self._time +'['+ str(cpId)+'_'+ str(uniqueId)+ "] Network connection error or invalid url",1)
            raise(IoTConnectSDKException("02"))
