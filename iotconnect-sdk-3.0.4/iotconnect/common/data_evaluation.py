import sys
import string
from datetime import datetime
import json

from iotconnect.common.infinite_timer import infinite_timer
from iotconnect.IoTConnectSDKException import IoTConnectSDKException

aggrigate_type = [
    { "name": "min", "value": 1 },
    { "name": "max", "value": 2 },
    { "name": "sum", "value": 4 },
    { "name": "avg", "value": 8 },
    { "name": "count", "value": 16 },
    { "name": "lv", "value": 32 }
]
DATATYPE = {
    "NUMBER": 0,
    "STRING": 1,
    "OBJECT": 2,
    "FLOAT" : 3
}

class data_evaluation:
    _isEdge = False
    _attribute = None
    _data = {}
    
    def parseNum(self, x):
        try:
            if type(x) == int:
                return int(x)
            else:
                return float(x)
        except ValueError:
            return x
    
    def parseData(self, value):
        try:
            if value != None:
                if type(value) == str:
                    value = value.rstrip()
            else:
                value = ""
            return self.parseNum(value)
        except:
            return value
    
    def get_interval(self, config):
        try:
            tumblingWindow = ""
            if config["tw"] != None and config["tw"] != "":
                tumblingWindow = config["tw"]
            
            duration = 0
            if tumblingWindow != "":
                time = tumblingWindow[:-1]
                timetype = tumblingWindow[-1:]
                if timetype == "s":
                    duration = int(time)
                elif timetype == "m":
                    duration = int(time) * 60
                elif timetype == "h":
                    duration = int(time) * 60 * 60
                else:
                    duration = 0
            
            return duration
        except:
            return 0
    
    def process_data(self, config, parent, value):
        try:
            key = self.get_data_key(config, parent)
            if self.has_key(self._data, key) == False:
                return None
            
            _config = self._data[key]
            dataType = _config["dt"]
            dataValidation = _config["dv"]
            isValid = False
            # --------------------------------
            if dataType == DATATYPE["NUMBER"]:
                value = self.parseData(value)
                isValid = isinstance(value, (int, float))
                if isValid and dataValidation != None and dataValidation != "":
                    isValid = False
                    vlist = dataValidation.split(",")
                    if len(vlist) > 0:
                        for v in vlist:
                            if v.find("to") > -1:
                                vRange = v.split("to")
                                if(value >= float(vRange[0].strip('')) and value <= float(vRange[1].strip(''))):
                                    isValid = True
                            elif float(value) == float(v):
                                isValid = True
                # --------------------------------
            elif dataType == DATATYPE["STRING"]:
                isValid = True
                if isValid and dataValidation != None and dataValidation != "":
                    isValid = False
                    vlist = dataValidation.split(",")
                    if len(vlist) > 0:
                        for v in vlist:
                            if v.find("to") > -1:
                                vRange = v.split("to")
                                if(value >= int(vRange[0].strip()) and value <= int(vRange[1].strip())):
                                    isValid = True
                            elif str(value) == v.strip():
                                isValid = True
                # --------------------------------
            # --------------------------------
            if self._isEdge:
                if isValid and dataType == DATATYPE["NUMBER"] and self.has_key(_config, "values"):
                    _config["values"].append(value)
                    _config["current_value"] = value
            
            if self._isEdge == False:
                data = {}
                if isValid:
                    data[_config["ln"]] = value
                    return {"RPT": data}
                else:
                    data[_config["ln"]] = str(value).rstrip()
                    return {"FLT": data}
            else:
                return None
        except:
            raise(IoTConnectSDKException("09","dataevaluation"))
    
    def callBackTimer(self, arg):
        self.process_edge_data(arg["key"], arg["p"], arg["tg"])
    
    def data_count(self, values):
        try:
            return len(values)
        except:
            return 0
    
    def data_min(self, values):
        try:
            if len(values) > 0:
                return min(values)
            else:
                return None
        except:
            return None
    
    def data_max(self, values):
        try:
            if len(values) > 0:
                return max(values)
            else:
                return None
        except:
            return None
    
    def data_avg(self, values):
        try:
            if len(values) > 0:
                return sum(values) / len(values)
            else:
                return None
        except:
            return None
    
    def data_sum(self, values):
        try:
            if len(values) > 0:
                return sum(values)
            else:
                return None
        except:
            return None
    
    def data_lv(self, values):
        try:
            if len(values) > 0:
                return values[len(values) - 1]
            else:
                return None
        except:
            return None
    
    def process_aggregate(self, config):
        values = []
        if self.has_key(config, "values") and len(config["values"]) > 0:
            values = config["values"]
        
        if len(values) == 0:
            return None
        
        agg_type = ""
        if self.has_key(config, "agt") and config["agt"] != "":
            agg_type = config["agt"]
        
        if agg_type == "":
            return None
        
        final = []
        #final.append(int(agg_type))
        for atype in aggrigate_type:
            value = atype["value"]
            name = atype["name"]
            if int(agg_type) & value:
                final.append(getattr(self, 'data_%s' % name)(values))
        
        return final
    
    def process_edge_data(self, key, p, tg):
        edgeData = []
        final = {}
        try:
            if key == "1":
                final[p] = {}
                for config in self._data:
                    ln = self._data[config]["ln"]
                    data = self.process_aggregate(self._data[config])
                    if data != None:
                        final[p][ln] = data
                    self._data[config]["values"] = []
                if len(final[p]) > 0:
                        pass
                else:
                    final={} 
            else:
                for config in self._data:
                    if config == key:
                        ln = self._data[config]["ln"]
                        data = self.process_aggregate(self._data[config])
                        if data != None:
                            final[ln] = data
                        self._data[config]["values"] = []       
        except:
            print("Error while process aggregate...")
        if len(final) > 0:
                edgeData.append(final)
        if len(edgeData) > 0:
            attr_data = { "tg": tg, "d": edgeData}
            if self.listner_callback:
                self.listner_callback(attr_data)

    def reset_get_rule_data(self):
        for i in range(0,len(self._attribute["d"])):
            self._attribute["d"][i]['current_value']=None

    def get_rule_data(self):
        try:
            if self._isEdge == False:
                return None
            
            obj = {
                "p": self._attribute["p"],                
                "st": "",
                "d": []
            }
            for data in self._attribute["d"]:
                if data["current_value"] != None :
                    child = {                    
                        "ln": data["ln"],
                        "v": data["current_value"],
                        "tg":data["tg"]
                    }
                    obj["d"].append(child)
            return obj
        except:
            return None
    
    def destroyed(self):
        try:
            if self.listner_callback != None:
                self.listner_callback = None
            
            if self._data != None:
                del(self._data)
            
            if self._timer != None and len(self._timer) > 0:
                for timer in self._timer:
                    timer.cancel()
                del(self._timer)
        except:
            print("Error while destroyed data evalution")
    
    def get_data_key(self, config, parent):
        try:
            if parent == "":
                return config["ln"] + config["tg"]
            else:
                return parent + config["ln"] + config["tg"]
        except:
            return "-1"
    
    def has_key(self, data, key):
        try:
            return key in data
        except:
            return False
    
    @property
    def _timestamp(self):
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    def __init__(self, isEdge, attribute, listner):
        self._data = {}
        self._isEdge = isEdge
        self._attribute = json.loads(json.dumps(attribute))
        self._timer = []
        
        if listner != None:
            self.listner_callback = listner
        
        name = self._attribute["p"]
        for data in self._attribute["d"]:
            key = self.get_data_key(data, name)
            self._data[key] = data
            if self._isEdge:
                self._data[key]["values"] = []
                self._data[key]["current_value"] = None
                if name == "":
                    self._data[key]["name"] = data["ln"]
                else:
                    self._data[key]["name"] = name + "." + data["ln"]
        
        if self._isEdge:
            if name != "":
                _key = "1"
                _tg = str(self._attribute["tg"])
                _p = str(self._attribute["p"])
                _interval = self.get_interval(self._attribute)
                if _interval > 0:
                    _timer = infinite_timer(_interval, self.callBackTimer, [{ "key": _key, "p": _p, "tg": _tg }])
                    _timer.start()
                    self._timer.append(_timer)
                else:
                    raise(IoTConnectSDKException("08", name))
            else:
                _p = ""
                for _key in self._data:
                    _key = str(_key)
                    _tg = str(self._data[_key]["tg"])
                    _interval = self.get_interval(self._data[_key])
                    if _interval > 0:
                        _timer = infinite_timer(_interval, self.callBackTimer, [{ "key": _key, "p": _p, "tg": _tg }])
                        _timer.start()
                        self._timer.append(_timer)
                    else:
                        raise(IoTConnectSDKException("08", _key))
