
class SDKOptions:
    def __init__(self, sdkOptions: dict):
        self.SSLKeyPath = sdkOptions['certificate']['SSLKeyPath']
        self.SSLCertPath = sdkOptions['certificate']['SSLCertPath']
        self.SSLCaPath = sdkOptions['certificate']['SSLCaPath']

        self.skipValidation = sdkOptions['skipValidation']
        self.discoveryUrl = sdkOptions['discoveryUrl']
        self.IsDebug = sdkOptions['IsDebug']