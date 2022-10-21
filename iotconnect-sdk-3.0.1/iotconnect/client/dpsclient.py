import sys
import os
import ssl as ssl
import json
if ('linux' in sys.platform) and (sys.version_info >=(3,5)):
    import jsonlib
import time
import threading
from iothub_client import *
from iotconnect.IoTConnectSDKException import IoTConnectSDKException

authType = {
    "TPM": 4
}

DPSMSGTYPE = {
    "DEVICE_CREATED": 9,
    "DEVICE_CONNECTED": 10
}

class dpsclient:
    _name = None
    _auth_type = None
    _sdk_config = None
    _config = None
    _client = None
    _keepalive = 60
    _isConnected = False
    _rc_status = None
    _send_status = None
    _twin_upadate=False
    _disconnect_msg='{"cmdType": "0x16","data": {"cpId":"_cpId","guid": "","uniqueId":"_uniqueId","command": "False","ack": "False","ackId": "","cmdType": "0x16"}}'
    _connect_msg='{"cmdType": "0x16","data": {"cpId":"_cpId","guid": "","uniqueId":"_uniqueId","command": "True","ack": "False","ackId": "","cmdType": "0x16"}}'

    def _on_connect(self, result, reason, user_context):
        if result != IoTHubConnectionStatus.AUTHENTICATED:
            self._isConnected = False
        else:
            self._isConnected = True
        self._rc_status = result

    def _on_message(self, message, counter):
        try:
            if self._client == None:
                return
            message_buffer = message.get_bytearray()
            size = len(message_buffer)
            data = message_buffer[:size]
            print(data)
            if ('linux' in sys.platform) and (sys.version_info >=(3,5)):
                msg=jsonlib.read(data)
            else:
                try:
                    msg = json.load(data.decode('utf-8'))
                except:
                    try:
                        msg=json.loads(data.decode('utf-8'))
                    except:
                        return IoTHubMessageDispositionResult.ABANDONED 
            if self._onMessage != None:
                self._onMessage(msg)
            return IoTHubMessageDispositionResult.ACCEPTED
        except:
            return IoTHubMessageDispositionResult.ABANDONED
    
    def _on_confirmation(self, message, result, user_context):
        self._send_status = result
    
    def Disconnect(self):
        try:
            if self._client != None:
                self._isConnected = False
                self._client = None
                self._onMessage(json.loads(self._disconnect_msg))
        except:
            self._client = None
    
    def Send(self, data):
        try:
            if self._client == None:
                return False
            if self._isConnected == False:
                return False
            
            self._send_status = None
            message = IoTHubMessage(json.dumps(data))
            if self._client:
                self._client.send_event_async(message, self._on_confirmation, None)
            
            while self._send_status == None and self._isConnected == True:
                time.sleep(0.1)
            
            if self._send_status == IoTHubClientConfirmationResult.OK:
                return True
            else:
                return False
        except:
            return False
    
    def send_reported_state_callback(self,status_code, user_context):
        self._twin_upadate=True

    def SendTwinData(self,data):
        if self._client == None:
            return False
        data=json.dumps(data)
        self._client.send_reported_state(data, len(data),self.send_reported_state_callback, None)
        return True

    def device_twin_callback(self,update_state, payload, client_as_user_context):
        if self._client == None:
            return 
        self._onTwinMessage(payload)
    
    def _init_dps(self):
        try:
            self.Disconnect()
            self._client = IoTHubClient(str(self._config["h"]), str(self._config['id']), IoTHubSecurityType.SAS, IoTHubTransportProvider.MQTT)
            self._client.set_option("messageTimeout", 1)
            self._client.set_option("keepalive", self._keepalive)
            self._client.set_connection_status_callback(self._on_connect, 0)
            self._client.set_retry_policy(IoTHubClientRetryPolicy.RETRY_INTERVAL, 0)
            self._client.set_message_callback(self._on_message, 0)
            self._client.set_device_twin_callback(self.device_twin_callback,  self._client)
            while self._rc_status == None:
                time.sleep(0.5)
            
            if self._rc_status == IoTHubConnectionStatus.AUTHENTICATED:
                self._onMessage(json.loads(self._connect_msg))
                print("Protocol Initialized...")
            else:
                raise(IoTConnectSDKException("06", "Connection refused - not authorised"))
        except Exception as ex:
            raise(ex)
    
    @property
    def isConnected(self):
        return self._isConnected
    
    @property
    def name(self):
        return "dps"
    
    def __init__(self, auth_type, config, sdk_config, onMessage,onTwinMessage):
        self._auth_type = auth_type
        self._config = config
        self._sdk_config = sdk_config
        self._onMessage = onMessage
        self._onTwinMessage = onTwinMessage
        self._init_dps()
