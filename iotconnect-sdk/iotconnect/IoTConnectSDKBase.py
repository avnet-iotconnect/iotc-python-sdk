
import sys
import os.path
import json
import time
import datetime

from base64 import b64encode, b64decode
from hashlib import sha256
from hmac import HMAC

if sys.version_info >= (3, 5):
    import http.client as httplib
    import urllib.request as urllib
    from urllib.parse import urlparse, quote_plus, urlencode
else:
    import httplib
    from urllib import quote_plus, urlencode
    import urllib2 as urllib
    from urlparse import urlparse


class IoTConnectSDKBase:
    _config = None
    _debug_error_path = None
    _debug_output_path = None

    @property
    def _timestamp(self):
        return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    @property
    def _time(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.000")
    
    @property
    def _debug(self):
        try:
            if self._config != None and self._config["IsDebug"]:
                return True
            else:
                return False
        except:
            return False
        
    @property
    def _validation(self):
        try:
            if self._config != None and self._config["skipValidation"]:
                return True
            else:
                return False
        except:
            return False
        
    @property
    def _discoveryUrl(self):
        try:
            if self._config != None and ("discoveryUrl" in self._config) and self._config["discoveryUrl"] and "http" in self._config["discoveryUrl"]:
                return True
            else:
                return False
        except:
            return False
    
    @property
    def _devicePrimaryKey(self):
        try:
            if self._config != None and self._config["devicePrimaryKey"]:
                return True
            else:
                return False
        except:
            return False
        
    @property
    def _offlineStorage(self):
        try:
            if self._config != None and self._config["offlineStorage"]:
                options = self._config["offlineStorage"]
                if ("disabled" in options) and ("availSpaceInMb" in options) and ("fileCount" in options):
                    if options["disabled"] == False:
                        return True
                    else: 
                        return False
                else:
                    return False
            else:
                return False
        except:
            return False
    
    def is_not_blank(self, s):
        return bool(s and s.strip())
    
    def has_key(self, data, key):
        try:
            return key in data
        except:
            return False
    
    def get_file(self):
        debug_path = os.path.join(sys.path[0], "logs")
        path_staus = os.path.exists(debug_path)
        if path_staus:
            for sub_folder in ["debug"]:
                debug_path = os.path.join(debug_path,sub_folder)                    
                path_staus = os.path.exists(debug_path)
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
    
    def write_debuglog(self, msg, is_error):
        if self._debug:
            if is_error:
                if self._debug_error_path:
                    with open(self._debug_error_path, "a") as dfile:
                        dfile.write(msg+'\n')
            else:
                if self._debug_output_path:
                    with open(self._debug_output_path,"a") as dfile:
                        dfile.write(msg+'\n')

    def valid_certificate(self):
        try:
            if self._config != None and ("certificate" in self._config) and self._config["certificate"] and len(self._config["certificate"]) == 3:
                cert = self._config["certificate"]
                isvalid = 0
                for prop in cert:
                    if os.path.isfile(cert[prop]) == False:
                        isvalid = 5
                        break
                return isvalid
            else:
                return 1
        except:
            return 1
    
    def get_base_url(self, sId, cpId = None, env = None):
        try:
            if not cpId:
                base_url = "/api/v2.1/dsdk/sid/" + sId
                base_url = self._config["discoveryUrl"] + base_url
            else:
                if self._pf == "az":
                    base_url = "/api/v2.1/dsdk/cpid/"+ cpId +"/env/" + env
                if self._pf == "aws":
                    base_url = "/api/v2.1/dsdk/cpid/"+ cpId +"/env/" + env + "?pf=aws"
                else:
                    base_url = "/api/v2.1/dsdk/cpid/"+ cpId +"/env/" + env                        
                base_url = self._config["discoveryUrl"] + base_url

            res = urllib.urlopen(base_url).read().decode("utf-8")
            data = json.loads(res)
            #print(data)
            # pf = None
            a = (data['d'].keys())
            if 'pf' in a:
                # print(pf)
                return data['d']["bu"], data['d']["pf"]
            else:
                pf = 'aws'
                return data['d']["bu"], pf  
        except Exception as ex:
            print (ex.message)
            return None
    
    def post_call(self, url, uniqueId):
        try:
            url = url+"/uid/" + uniqueId
            res = urllib.urlopen(url).read().decode("utf-8")
            data = json.loads(res)
            if self.has_key(data, "d") == False:
                data = None
            else:
                data = data["d"]
            return data
        except:
            return None

    def generate_sas_token(self, uri, key, policy_name = None, expiry = 31536000):
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
    
    def find_df(self, seconds): 
        seconds = seconds % (24 * 3600) 
        hour = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        times= datetime.datetime.strptime("%02d%02d%02d" % (hour, minutes, seconds),'%H%M%S')
        return times
