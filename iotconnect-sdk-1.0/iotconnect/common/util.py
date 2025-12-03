
import os.path
from datetime import datetime
from iotconnect.IoTConnectSDKException import IoTConnectSDKException

DATATYPE = {
    "INT"     : 1,
    "LONG"    : 2,
    "FLOAT"   : 3,
    "STRING"  : 4,
    "Time"    : 5,
    "Date"    : 6,
    "DateTime": 7,
    "BIT"     : 8,
    "Boolean" : 9,
    "LatLong" : 10,
    "OBJECT"  : 12
}

class util:

    @staticmethod
    def parseNum(x, sign):
        try:
            if type(x) == str:
                if sign and '.' in x:
                    return float(x)
                else:
                    return int(x)
            elif type(x) == int:
                return int(x)
            else:
                return float(x)
        except ValueError:
            return x
    
    @staticmethod
    def parseData(value, sign):
        try:
            if value != None:
                if type(value) == str:
                    value = value.rstrip()
            else:
                value = ""
            return util.parseNum(value, sign)
        except:
            return value
    
    @staticmethod
    def parseDateTime(date_time, format):
        if type(date_time) == str:
            try:
                return bool(datetime.strptime(date_time, format))
            except:
                return False
        else:
            return False

    @staticmethod
    def DateTimeConversion(value, min_value, max_value, format, r_format):
        try:
            if min_value:
                min_value = min_value.replace(" ","")
                min_value = datetime.strptime(min_value, r_format)
                min_value = int(min_value.strftime(format))
            if max_value:
                max_value = max_value.replace(" ","")
                max_value = datetime.strptime(max_value, r_format)
                max_value = int(max_value.strftime(format))
            if value:
                t_value = datetime.strptime(value, r_format)
                t_value = int(t_value.strftime(format))

            return t_value, min_value, max_value
        except:
            return None, None, None
    
    @staticmethod
    def twin_validate(dataType, validation, value):
        try:
            dataValidation=validation
            isValid = False
            if dataType == DATATYPE["INT"] or dataType == DATATYPE["LONG"]:
                value = util.parseData(value,1)
                isValid=True
                if isinstance(value, (int)) and dataType == DATATYPE["INT"] and dataValidation != None and dataValidation != "" and value >= -(2**31) and value <= (2**31):
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

                if isinstance(value, (int)) and dataType == DATATYPE["LONG"] and dataValidation != None and dataValidation != "" and value >= -(2**63) and value <= (2**63):
                    isValid = False
                    vlist = dataValidation.split(",")
                    if len(vlist) > 0:
                        for v in vlist:
                            if v.find("to") > -1:
                                vRange = v.split("to")
                                if(value >= int(vRange[0].strip('')) and value <= int(vRange[1].strip(''))):
                                    isValid = True
                            elif int(value) == int(v):
                                isValid = True

                # --------------------------------
            elif dataType == DATATYPE["STRING"]:
                if type(value) == str:
                    isValid = True
                if isinstance(value, str) and dataValidation != None and dataValidation != "":
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

            elif dataType == DATATYPE["FLOAT"]:
                value = util.parseData(value,0)
                isValid = True
                if isinstance(value, (int,float)) and dataValidation != None and dataValidation != "":
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

            elif dataType == DATATYPE["DateTime"]:
                isValid = util.parseDateTime(value,"%Y-%m-%dT%H:%M:%S.000Z")
                if  isValid and dataValidation != None and dataValidation != "":
                    vlist = dataValidation.split(",")
                    if len(vlist) > 0:
                        for v in vlist:
                            if v.find("to") > -1:
                                vRange = v.split("to")
                                t_value,min_value,max_value = util.DateTimeConversion(value,str(vRange[0].strip('')),str(vRange[1].strip('')),"%Y%m%d%H%M%S","%Y-%m-%dT%H:%M:%S.000Z")
                                if t_value and min_value and max_value:
                                    if( t_value >= min_value and t_value <= max_value):
                                        isValid= True
                            else:
                                t_value,min_value,_ = util.DateTimeConversion(value,str(v.strip('')),0,"%Y%m%d%H%M%S","%Y-%m-%dT%H:%M:%S.000Z")
                                if t_value == min_value:
                                    isValid = True

            elif dataType == DATATYPE["Date"]:
                isValid = util.parseDateTime(value,"%Y-%m-%d")
                if  isValid and dataValidation != None and dataValidation != "":
                    vlist = dataValidation.split(",")
                    if len(vlist) > 0:
                        for v in vlist:
                            if v.find("to") > -1:
                                vRange = v.split("to")
                                t_value,min_value,max_value = util.DateTimeConversion(value,str(vRange[0].strip('')),str(vRange[1].strip('')),"%Y%m%d","%Y-%m-%d")
                                if t_value and min_value and max_value:
                                    if( t_value >= min_value and t_value <= max_value):
                                        isValid= True
                            else:
                                t_value,min_value,_ = util.DateTimeConversion(value,str(v.strip('')),0,"%H%M%S","%Y-%m-%d")
                                if t_value == min_value:
                                    isValid = True

            elif dataType == DATATYPE["Time"]:
                isValid = util.parseDateTime(value,"%H:%M:%S")
                if  isValid and dataValidation != None and dataValidation != "":
                    vlist = dataValidation.split(",")
                    if len(vlist) > 0:
                        for v in vlist:
                            if v.find("to") > -1:
                                vRange = v.split("to")
                                t_value,min_value,max_value = util.DateTimeConversion(value,str(vRange[0].strip('')),str(vRange[1].strip('')),"%H%M%S","%H:%M:%S")
                                if t_value and min_value and max_value:
                                    if( t_value >= min_value and t_value <= max_value):
                                        isValid= True
                            else:
                                t_value,min_value,_= util.DateTimeConversion(value,str(v.strip('')),0,"%H%M%S","%H:%M:%S")
                                if t_value == min_value:
                                    isValid = True

            elif dataType == DATATYPE["BIT"]:
                if type(value) == int and (value == 0 or value == 1):
                    isValid = True
                if dataValidation != None and dataValidation != "":
                    isValid = False
                    vlist = dataValidation.split(",")
                    if len(vlist) > 0:
                        for v in vlist:
                            if value == int(v):
                                isValid = True

            elif dataType == DATATYPE["Boolean"]:
                if type(value) == bool and (value == True or value == False):
                    isValid = True
                if dataValidation != None and dataValidation != "":
                    isValid = False
                    vlist = dataValidation.split(",")
                    if len(vlist) > 0:
                        for v in vlist:
                            if v == "true" or v == "True":
                                v=True
                            elif v == "false" or v == "False":
                                v=False
                            try:
                                if value == bool(v):
                                    isValid = True
                            except:
                                isValid = False
            return isValid
        except:
            raise(IoTConnectSDKException("09","Twin Validation"))

    @staticmethod
    def is_not_blank(s):
        return bool(s and s.strip())
    
    @staticmethod
    def cert_validate(cert, auth_type):
        if cert == None:
            return False
        
        isvalid = True
        sslKeyPath = cert["SSLKeyPath"] if cert["SSLKeyPath"] else None
        sslCertPath = cert["SSLCertPath"] if cert["SSLCertPath"] else None
        sslCaPath = cert["SSLCaPath"] if cert["SSLCaPath"] else None
        
        if sslKeyPath and util.is_not_blank(sslKeyPath) and os.path.isfile(sslKeyPath) == True:
            if (sslKeyPath.lower().endswith(".pem") != True or sslKeyPath.lower().endswith(".key") != True) == False:
                isvalid = False
        else:
            isvalid = False

        if isvalid == True and sslCertPath and util.is_not_blank(sslCertPath) and os.path.isfile(sslCertPath) == True:
            if (sslCertPath.lower().endswith(".crt") != True or sslCertPath.lower().endswith(".pem") != True) == False:
                isvalid = False
        else:
            isvalid = False
        
        if auth_type != 3:
            if isvalid == True and sslCaPath and util.is_not_blank(sslCaPath) and os.path.isfile(sslCaPath) == True:
                if sslCaPath.lower().endswith(".pem") != True:
                    isvalid = False
            else:
                isvalid = False
        
        if auth_type == 3: #CA_SELF_SIGNED
            if isvalid == True and sslCaPath and util.is_not_blank(sslCaPath) and os.path.isfile(sslCaPath) == True:
                if sslCaPath.lower().endswith(".pem") != True:
                    isvalid = False

        return isvalid

    @staticmethod
    def der_hex_to_pem(der_hex, cert_type="CERTIFICATE"):
        """
        Convert DER hex string to PEM format

        Args:
            der_hex: Certificate or key in DER hex format
            cert_type: Type of certificate - "CERTIFICATE", "RSA PRIVATE KEY", "PRIVATE KEY"

        Returns:
            PEM formatted string
        """
        try:
            import base64

            # Convert hex string to bytes
            der_bytes = bytes.fromhex(der_hex)

            # Convert to base64
            base64_data = base64.b64encode(der_bytes).decode('utf-8')

            # Split into 64-character lines
            lines = [base64_data[i:i+64] for i in range(0, len(base64_data), 64)]

            # Format as PEM
            pem_data = "-----BEGIN {}-----\n".format(cert_type)
            pem_data += "\n".join(lines)
            pem_data += "\n-----END {}-----\n".format(cert_type)

            return pem_data

        except Exception as ex:
            print("DER hex to PEM conversion failed: " + str(ex))
            return None

    @staticmethod
    def save_pem_file(pem_data, file_path):
        """
        Save PEM data to a file

        Args:
            pem_data: PEM formatted string
            file_path: Path to save the file

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(file_path, 'w') as f:
                f.write(pem_data)
            return True
        except Exception as ex:
            print("Failed to save PEM file: " + str(ex))
            return False

    @staticmethod
    def convert_and_save_certificates(dc_hex, pk_hex, cert_path, key_path):
        """
        Convert DER hex certificates to PEM and save to files

        Args:
            dc_hex: Device certificate in DER hex format
            pk_hex: Private key in DER hex format
            cert_path: Path to save the certificate file
            key_path: Path to save the key file

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert device certificate
            cert_pem = util.der_hex_to_pem(dc_hex, "CERTIFICATE")
            if not cert_pem:
                return False

            # Convert private key
            key_pem = util.der_hex_to_pem(pk_hex, "PRIVATE KEY")
            if not key_pem:
                return False

            # Save certificate
            if not util.save_pem_file(cert_pem, cert_path):
                return False

            # Save private key
            if not util.save_pem_file(key_pem, key_path):
                return False

            print("Certificates converted and saved successfully")
            return True

        except Exception as ex:
            print("Certificate conversion and save failed: " + str(ex))
            return False
