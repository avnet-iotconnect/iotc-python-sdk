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