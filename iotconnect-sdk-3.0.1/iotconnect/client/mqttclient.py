import os
import ssl as ssl
import paho.mqtt.client as mqtt
import json
import time
from iotconnect.IoTConnectSDKException import IoTConnectSDKException

authType = {
	"KEY": 1,
	"CA_SIGNED": 2,
	"CA_SELF_SIGNED": 3
}

class mqttclient:
    _name = None
    _auth_type = None
    _sdk_config = None
    _config = None
    _subTopic = None
    _pubTopic = None
    _twin_pub_topic = None
    _twin_sub_topic = None
    _twin_sub_res_topic = None
    _client = None
    _keepalive = 60
    _onMessage = None
    _onTwinMessage = None
    _isConnected = False
    _rc_status = None
    _mqtt_status = {
        0: "MQTT: Connection successful",
        1: "MQTT: Connection refused - incorrect protocol version",
        2: "MQTT: Connection refused - invalid client identifier",
        3: "MQTT: Connection refused - server unavailable",
        4: "MQTT: Connection refused - bad username or password",
        5: "MQTT: Connection refused - not authorised"
    }
    
    def _on_connect(self, mqtt_self, client, userdata, rc):
        if rc != 0:
            self._isConnected = False
        else:
            self._isConnected = True
        if self._isConnected and mqtt_self:
            mqtt_self.subscribe(self._subTopic)
            mqtt_self.subscribe(self._twin_sub_topic)
            mqtt_self.subscribe(self._twin_sub_res_topic)
        self._rc_status = rc
    
    def _on_disconnect(self, client, userdata, rc):
        self._rc_status = rc
        self._isConnected = False
    
    def _on_message(self, client, userdatam, msg):
        if msg.topic.find(self._subTopic[:-1]) > -1 and self._onMessage != None:
            self._onMessage(msg)
        if msg.topic.find(self._twin_sub_topic[:-1]) > -1 and self._onTwinMessage != None:
            self._onTwinMessage(msg)
        if msg.topic.find(self._twin_sub_res_topic[:-1]) > -1:
            self._onTwinMessage(msg)
    
    def _connect(self):
        try:
            try:
                if self._isConnected == False:
                    self._client.connect(self._config["h"], self._config["p"], self._keepalive)
                    self._client.loop_start()
            except Exception as ex:
                self._rc_status = 5
            
            while self._rc_status == None:
                time.sleep(0.5)
            
            if self._rc_status == 0:
                print("Protocol Initialized...")
                self._client.publish(self._twin_pub_res_topic, payload="", qos=1)
            else:
                raise(IoTConnectSDKException("06", self._mqtt_status[self._rc_status]))
        except Exception as ex:
            raise(ex)
    
    def _validateSSL(self, certificate):
        is_valid_path = True
        if certificate == None:
            raise(IoTConnectSDKException("01", "Certificate info"))
        
        for prop in certificate:
            if os.path.isfile(certificate[prop]) == False:
                is_valid_path = False
        
        if is_valid_path:
            return certificate
        else:
            raise(IoTConnectSDKException("05"))
    
    def Disconnect(self):
        try:
            if self._client != None:
                self._client.disconnect()
                while self._isConnected == True:
                    time.sleep(1)
                self._client.loop_stop()
                self._client = None
            self._rc_status = None
        except:
            self._client = None
            self._rc_status = None
    
    def Send(self, data):
        try:
            _obj = None
            if self._isConnected:
                if self._client and self._pubTopic != None:
                    _obj = self._client.publish(self._pubTopic, payload=json.dumps(data))
            
            if _obj and _obj.rc == 0:
                return True
            else:
                return False
        except:
            return False
    
    def SendTwinData(self, data):
        try:
            _obj = None
            if self._isConnected:
                if self._client and self._twin_pub_topic != None:
                    _obj = self._client.publish(self._twin_pub_topic, payload=json.dumps(data), qos=1)
            
            if _obj and _obj.rc == 0:
                return True
            else:
                return False
        except:
            return False
    
    def _init_mqtt(self):
        try:
            self.Disconnect()

            self._client = mqtt.Client(client_id=self._config['id'], clean_session=True, userdata=None, protocol=mqtt.MQTTv311)
            #Check Auth Type
            if self._auth_type == authType["KEY"]:
                self._client.username_pw_set(self._config["un"], self._config["pwd"])                
                self._client.tls_set(ca_certs = None, tls_version = ssl.PROTOCOL_TLSv1)
            elif self._auth_type == authType["CA_SIGNED"]:
                self._client.username_pw_set(self._config["un"], password=None)
                cert_setting = self._validateSSL(self._sdk_config["certificate"])
                if cert_setting != None:
                    self._client.tls_set(ca_certs=None, certfile=str(cert_setting["SSLCertPath"]), keyfile=str(cert_setting["SSLKeyPath"]), cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2, ciphers=None)
                    self._client.tls_insecure_set(False)
            elif self._auth_type == authType["CA_SELF_SIGNED"]:
                self._client.username_pw_set(self._config["un"], password=None)
                cert_setting = self._validateSSL(self._sdk_config["certificate"])
                if cert_setting != None:
                    self._client.tls_set(ca_certs=None, certfile=str(cert_setting["SSLCertPath"]), keyfile=str(cert_setting["SSLKeyPath"]), cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2, ciphers=None)
                    self._client.tls_insecure_set(False)
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message
            self._client.disable_logger()
            if self._client != None:
                self._connect()    
        except Exception as ex:
            raise(ex)
    
    @property
    def isConnected(self):
        return self._isConnected
    
    @property
    def name(self):
        return self._config["n"]
    
    def __init__(self, auth_type, config, sdk_config, onMessage, onTwinMessage = None):
        self._auth_type = auth_type
        self._config = config
        self._sdk_config = sdk_config
        self._onMessage = onMessage
        self._onTwinMessage = onTwinMessage
        self._subTopic = str(config['sub'])
        self._pubTopic = str(config['pub'])
        self._twin_pub_topic = str(sdk_config['twin_pub_topic'])
        self._twin_sub_topic = str(sdk_config['twin_sub_topic'])
        self._twin_sub_res_topic = str(sdk_config['twin_sub_res_topic'])
        self._twin_pub_res_topic = str(sdk_config['twin_pub_res_topic'])
        self._init_mqtt()
