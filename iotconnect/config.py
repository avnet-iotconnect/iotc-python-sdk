topics = {

}

DEVICE_IDENTITY_OPTIONS = [
    "HELLO"
    "ATT",
    "SETTING",
    "DEVICE",
    "RULE",

]

DEVICE_IDENTITY_MESSAGES = {
    "HELLO": 200,
    "ATT": 201,
    "SETTING": 202,
    "RULE": 203,
    "DEVICE": 204
}

CLOUD_TO_DEVICE_CODES = {
    0: 'DCOMM',
    1: 'FIRMWARE',
    2: 'MODULE',
    101: 'U_ATTRIBUTE',
    102: 'U_SETTING',
    103: 'U_RULE',
    104: 'U_DEVICE',
    105: 'DATA_FRQ',
    106: 'U_barred',
    107: 'D_Disabled',
    108: 'D_Released',
    109: 'STOP',
    110: 'Start_Hr_beat',
    111: 'Stop_Hr_beat',
    116: 'is_connect',
    'sync': 'SYNC',
    'resetpwd': 'RESETPWD',
    'updatecrt': 'UCART'
}

config_json = {
    "env": "DEV",
    "sdk_lang": "M_PYTHON",
    "sdk_version": "3.0.2",
    "api_version": "2016-02-03",
    "api_path": "/devices/{clientId}/messages/events?api-version={api_version}",
    "api_global_prov_url": "global.azure-devices-provisioning.net",
    "az": {
        "twin_pub_topic": "$iothub/twin/PATCH/properties/reported/?$rid=1",
        "twin_sub_topic": "$iothub/twin/PATCH/properties/desired/#",
        "twin_sub_res_topic": "$iothub/twin/res/#",
        "twin_pub_res_topic": "$iothub/twin/GET/?$rid=0"
    },
    "aws": {
        "twin_pub_topic": "$aws/things/{Cpid_DeviceID}/shadow/name/{Cpid_DeviceID}_twin_shadow/report",
        "twin_sub_topic": "$aws/things/{Cpid_DeviceID}/shadow/name/{Cpid_DeviceID}_twin_shadow/property-shadow",
        "twin_sub_res_topic": "$aws/things/{Cpid_DeviceID}/shadow/name/{Cpid_DeviceID}_twin_shadow/get/all",
        "twin_pub_res_topic": "$aws/things/{Cpid_DeviceID}/shadow/name/{Cpid_DeviceID}_twin_shadow/get"
    }
}