# From the SDK sample's configuration to your firmware

The SDK repository ships `sample/iotconnect-sdk-1.0-firmware-python_msg-2_1.py`. Most developers start
there. It keeps the device identity and options as literals at the top of the file. This page maps each
of those literals to where the value comes from, how this skill handles it, and what to change before
the code runs on a real device.

## Project layout

Keep each device's files together from the moment the device is created in the platform: download its
certificates and export its template at the same time.

```
<project>/
  certs/<UniqueId>/     pk_<name>.pem  cert_<name>.crt  AmazonRootCA1.pem   (git-ignored)
  certs/                the same three files directly, when the project has one device
  templates/            <template>.json exported from the platform  (template/ also works)
  iotc.env              IOTC_* settings, one file per device if there are several  (git-ignored)
  .gitignore            certs/  and  iotc.env  (and env/ if you keep one env file per device)
```

- Certificates belong to one device; a template is shared by every device of that type, so name the
  template file after the template, not the device.
- Delete the downloaded `*-certificates.zip` after extracting it; it holds a second copy of the private key.
- The template code (for example `Test0511`) and the certificate file names are not proof of the device's
  unique id. Take `IOTC_UNIQUE_ID` from the device page in the platform.
- `iotc.env` is loaded automatically by the firmware starters and `preflight.py` (from the current
  folder, the script's folder or its parent; `IOTC_ENV_FILE` points elsewhere). Variables already set in
  the environment win, and relative paths in the file are relative to the file, so the firmware can run
  from any folder.
- `scripts/preflight.py` run from the project folder finds the files in this layout. When they are not in
  `iotc.env` yet, it prints the `IOTC_KEY`, `IOTC_CERT` and `IOTC_CA` lines to add. It fails when the private key or `iotc.env` could be committed, and warns about a
  leftover certificate zip.

## The configuration block, setting by setting

| In the sample | Env var in this skill | Where the value comes from | Notes |
|---|---|---|---|
| `UniqueId = "reInvent"` | `IOTC_UNIQUE_ID` | the device you registered in the platform | the device must be **Active and Acquired**, or the constructor can wait for ever |
| `SdkOptions["cpid"]` | `IOTC_CPID` | platform: Settings, Key Vault | |
| `SdkOptions["env"]` | `IOTC_ENV` | platform: Settings, Key Vault | needed together with `cpid` |
| `SdkOptions["sId"]` | `IOTC_SID` | solution id | alternative to `cpid` + `env`; the SDK uses it when set |
| `SdkOptions["pf"]` | `IOTC_PF` | `aws` or `az`, as for your environment | sent in the discovery request; the discovery reply may state the platform itself |
| `SdkOptions["discoveryUrl"]` | `IOTC_DISCOVERY_URL` | `https://discovery.iotconnect.io`, or the host for your environment | the sample's comments say the EU Azure environment uses `https://eudiscovery.iotconnect.io`. Must contain `http` |
| `certificate.SSLKeyPath` | `IOTC_KEY` | device private key from the platform | |
| `certificate.SSLCertPath` | `IOTC_CERT` | device certificate | |
| `certificate.SSLCaPath` | `IOTC_CA` | root CA | file name must end in `.pem` or ERR[05] |
| `devicePrimaryKey` | `IOTC_PRIMARY_KEY` | platform: Device, select the device, Info tab, Connection Info, Device Connection | symmetric-key devices only. Use it instead of `certificate` |
| `interval = 10` | `IOTC_SEND_INTERVAL` | your choice | never below the template `dataFrequency`, or sends are dropped |
| `IsDebug: True` | `IOTC_DEBUG` | | prints payloads. Off in production |
| `offlineStorage` | edit in firmware | your device | see "Things to change" below |
| `offlineStorage.keepalive` | edit in firmware | | has no effect there; move it to a top-level `keepalive` |
| `skipValidation` | edit in firmware | | `True` turns off template-based checks. Leave `False` |
| `CameraOptions` | edit in firmware | camera device | `references/video-and-file-upload.md` |

### Certificate file names by platform

The sample's comments give the usual names. Check the names of the files you were issued.

| File | AWS | Azure |
|---|---|---|
| private key | `pk_<devicename>.pem` | `device.key` |
| certificate | `cert_<devicename>.crt` | `device.pem` |
| root CA | `root-CA.pem` | `rootCA.pem` |

Use forward slashes in paths on Windows and Linux (`E:/folder/cert.pem`, `/home/pi/certs/cert.pem`).

## Turning a sample-style file into config

If the developer already has a firmware file that holds these literals, do not retype them:

```
python3 scripts/import_sample_config.py their_firmware.py              # prints the env file, secrets masked
python3 scripts/import_sample_config.py their_firmware.py -o iotc.env  # writes it (owner-only on Linux/macOS)
python3 scripts/import_sample_config.py their_firmware.py --report     # findings only
python3 scripts/preflight.py                                           # loads ./iotc.env by itself
```

The script parses the file and reads only module-level literals: `UniqueId`, `interval`, `SdkOptions`,
and `cpid`/`env`/`sId`/`pf` when an older sample keeps them outside `SdkOptions`. It does not run the
firmware or import the SDK, and it masks the primary key unless writing a file. It reports what is wrong
for a real device: placeholders, paths missing on this machine (with a hint for WSL or Windows paths),
a root CA not ending in `.pem`, `IsDebug` left on, a demonstration-sized or incomplete offline buffer,
`keepalive` in the wrong place, and a constructor call with the older 7-argument signature
(`IoTConnectSDK(uniqueId, sId, cpid, env, pf, sdkOptions, cb)`), which this SDK does not accept.
It exits 2 when the file cannot be parsed or holds no configuration.

`assets/iotc.env.example` is a blank file to fill in for a new device.

## Config to firmware: the flow

1. Collect the identity values above (or import them from an existing file).
2. Get the device template JSON (`references/device-template.md`).
3. Run `preflight.py` and fix every FAIL.
4. Start from `assets/firmware_template.py`. It loads `iotc.env` and reads the same `IOTC_*` variables, so
   the config feeds it without edits.
5. Generate the readings, commands and settings code with `template_tool.py skeleton`.
6. Validate a sample payload, run, then use the checklist in `SKILL.md`.

## Things to change when copying from the sample

| In the sample | Why it is not production-ready | What to do |
|---|---|---|
| Author's absolute paths, device name `reInvent` | they exist only on the author's machine | take paths and IDs from env vars |
| `IsDebug: True` | prints message payloads | `IOTC_DEBUG=0` |
| `availSpaceInMb: 0.01`, `fileCount: 5` | holds almost no data | size for the real storage and outage length. All of `disabled`, `availSpaceInMb` and `fileCount` must be present, or offline storage is not enabled |
| `"keepalive": 60` inside `offlineStorage` | never read there | put `keepalive` at the top level of `SdkOptions` |
| `while True` loop with `time.sleep(10)` and no telemetry | the telemetry call is only in the array test, and 10 s is shorter than the default 60 s data frequency; `Sdk.Dispose()` after the loop never runs | send `read_sensors()` at the template `dataFrequency` and stop through a flag or signal (the starter does this) |
| `sendBackToSDK` ignores `None` | `SendData` returns `None` when it did not try (not ready, inside the frequency window) | treat only `True` as sent |
| `"Firmware :: " + msg` in `InitCallback`, `DeviceChangCallback`, `attributeDetails`, and the child callbacks | raises `TypeError` if `msg` is not a string, and these callbacks receive dicts or lists | print `json.dumps(msg)` or `str(msg)` |
| `Sdk.sendAckCmd(..., 2, "sucessfull")` always | acknowledges success without doing the work | run the command, then send success or failure |
| OTA callback sends status `5` straight away | 5 is the right success status (the README's `0` is wrong), but the sample acknowledges success without downloading anything | ack 2 when downloading, then 5 or 1 after applying (`data-and-commands.md`) |
| `TwinUpdateCallback` copies every desired value into reported | reports values the device never applied | apply the value, then `UpdateTwin(key, converted_value)` |
| `except Exception as ex: print(ex)` | `IoTConnectSDKException` prints only the raw code | catch it separately and print `ex.message` |
| KVS WebRTC started when `KVS_TEST_CHANNEL_ARN` is set | a test hook | see `references/video-and-file-upload.md`; the variables it reads are `KVS_TEST_CHANNEL_ARN`, `AWS_CREDENTIAL_ENDPOINT` (optional) and `AWS_REGION` (default `us-east-1`) |
| `test_file_upload`, `test_array_data` flags | test helpers | file upload depends on the template `fileSupport` setting; array and object data must follow the template, and the sample says an attribute such as `temperature` must be included so the message goes to RPT |

## When the config is wrong: what you see

| Symptom | Likely config cause |
|---|---|
| `ERR[01]` | `cpid`/`sId` blank, `uniqueId` blank, or `discoveryUrl` without `http` |
| `AttributeError ... 'message'` | the discovery request failed: wrong `cpid`/`env`/`pf`/URL, or no network |
| `ERR[05]` | certificate path wrong, or the CA file name does not end in `.pem` |
| constructor never returns | device not Active and Acquired, or certificates belong to another device |
| data missing | see `device-template.md` and `troubleshooting.md` |
