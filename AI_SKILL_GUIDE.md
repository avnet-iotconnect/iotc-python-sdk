# Building firmware with the AI skill `iotconnect-python-firmware`

This SDK ships an **agent skill**: a package of instructions, reference notes and helper scripts that
an AI coding assistant (Claude Code or Kiro) loads when you ask it to work on /IOTCONNECT firmware.
With the skill installed, you describe your device in plain language and the assistant:

- writes the settings file for your device,
- checks certificates, settings, template and network before the first connection,
- writes firmware that follows your device template and the SDK's real behaviour,
- validates the telemetry payload, and
- helps you debug when data does not show up.

The skill is also useful without an AI. Its scripts run on their own (see "Using the scripts directly").

---

## 1. What you need

| | |
|---|---|
| Python | 3.6 or newer (3.11 recommended) |
| This SDK | installed: `pip install ./iotconnect-sdk-1.0` (or the `.tar.gz` from this repository) |
| An AI assistant | **Claude Code** (CLI, desktop or IDE extension), or **Kiro** (IDE 0.9 or newer, or Kiro CLI) |
| A device in /IOTCONNECT | created, **Active and Acquired**, with its certificates (X.509) or primary key (symmetric key) |
| The device template | exported as JSON from the platform (recommended) |

The skill is in this repository at `skills/iotconnect-python-firmware/`

---

## 2. Install the skill

Copy the **whole folder** into your firmware project. Keep the folder name `iotconnect-python-firmware`,
because both assistants require the folder name to match the skill name.

| Assistant | For one project (recommended) | For all your projects |
|---|---|---|
| Claude Code | `<project>/.claude/skills/iotconnect-python-firmware/` | `~/.claude/skills/iotconnect-python-firmware/` |
| Kiro | `<project>/.kiro/skills/iotconnect-python-firmware/` | `~/.kiro/skills/iotconnect-python-firmware/` |

From a clone of this repository:

```bash
cd <your firmware project>
mkdir -p .claude/skills .kiro/skills
cp -r <path to this repo>/skills/iotconnect-python-firmware .claude/skills/   # Claude Code
cp -r <path to this repo>/skills/iotconnect-python-firmware .kiro/skills/     # Kiro (optional)
ls .claude/skills/iotconnect-python-firmware                                   # SKILL.md  assets  references  scripts
```

Or from the release zip:

```bash
unzip iotconnect-python-firmware-v5.zip -d .claude/skills/          # Claude Code
unzip iotconnect-python-firmware-v5.zip -d .kiro/skills/            # Kiro (optional)
```

Then **start a new chat or session** in the project folder. Assistants read the list of skills when a
session starts. To check, ask *"Which skills do you have?"*. In Claude Code you can also type
`/iotconnect-python-firmware`.

> Kiro CLI with a custom agent: if the skill is not picked up, add
> `"resources": ["skill://.kiro/skills/*/SKILL.md"]` to the agent's configuration.

---

## 3. Set up your project folder

When you create a device in the platform, download its certificates and export its template **at the same
time**, into this layout:

```
<project>/
  certs/                 pk_<device>.pem  cert_<device>.crt  AmazonRootCA1.pem
  certs/<UniqueId>/      (the same three files, one folder per device, when you have several)
  template/  or  templates/
                         <template>.json  exported from the platform
  iotc.env               settings; the assistant writes it for you (section 4)
  firmware/              the assistant puts the firmware here
  .gitignore
```

**Before anything else, protect your secrets.** Add these lines to `.gitignore`:

```
certs/
iotc.env
__pycache__/
logs/
```

- `certs/` holds the device's **private key**. Never commit it.
- Delete the downloaded `*-certificates.zip` after extracting it, because it contains a second copy of the key.
- The root CA file name must end in `.pem`; the SDK rejects other names.
- The SDK writes `logs/debug/` and `logs/offline/` next to the script it runs, so a `firmware/` folder gets a
  `firmware/logs/` folder.

### Where each value comes from

| Value | Where to find it in /IOTCONNECT |
|---|---|
| Unique ID | the device's page. Do not guess it from the certificate file names or the template code |
| CPID and environment | Settings, then Key Vault |
| Platform | `aws` (or `az` for Azure) |
| Discovery URL | normally `https://discovery.iotconnect.io`; some environments have their own |
| Certificates | downloaded when the device was created |
| Template | the device's template, exported as JSON |

---

## 4. Configure: let the assistant do it

You do not need to write configuration files by hand. Give the assistant the values in your first prompt
and it writes `iotc.env` for you. The firmware and the check script load `iotc.env` automatically, so there
is nothing to `source` or `export`.

`iotc.env` looks like this (for reference; `assets/iotc.env.example` has every key):

```bash
IOTC_UNIQUE_ID='Test0511'
IOTC_CPID='<cpid>'
IOTC_ENV='<environment>'
IOTC_PF='aws'
IOTC_DISCOVERY_URL='https://discovery.iotconnect.io'
IOTC_KEY='certs/pk_Test0511.pem'
IOTC_CERT='certs/cert_Test0511.crt'
IOTC_CA='certs/AmazonRootCA1.pem'
IOTC_TEMPLATE='template/MyTemplate.json'
IOTC_SEND_INTERVAL='5'
IOTC_DEBUG='1'          # first tests only; set to 0 afterwards
```

- Paths are relative to the project folder, so the firmware runs from any working directory.
- An environment variable you set yourself always wins over the file.
- **Symmetric-key devices:** do not paste the `devicePrimaryKey` into the chat. Type it into
  `iotc.env` yourself as `IOTC_PRIMARY_KEY='...'`. For X.509 devices nothing in `iotc.env` is a secret; the
  assistant only needs the *paths* to the key files, never their contents.

---

## 5. Use it: example prompts

Start every request by naming the skill. That makes sure the assistant loads it.

### First firmware for a new device (start here)

> Use the iotconnect-python-firmware skill. Device Unique ID `Test0511`, CPID `<cpid>`, env `<env>`,
> platform `aws`. Certificates are in `certs/`, the template is in `template/`. Set up iotc.env, run
> preflight with `--check-network` and fix what fails, then write `firmware/test0511.py` for this template,
> sending the template's attributes every 5 seconds from stub readings, and validate a sample payload.
> Then run it for 60 seconds, stop it, and tell me what each SendData returned and why.

What you should see:
- Preflight: **0 failed**. Expect one warning about `PYTHONHTTPSVERIFY`; it is accurate and you fix it for production.
- Validation: **0 errors**.
- The run: `connection: True`, then `SendData -> True` at the template's data frequency.
- In the platform: the device's telemetry updating.

### Understand a template

> Summarise `template/MyTemplate.json` with the skill: what must my firmware send, with which Python types,
> how often, and which commands need acknowledgements?

### Bring over an existing sample or old firmware

> Use the skill's import_sample_config.py on `sample/my_old_firmware.py`, write iotc.env from it, list the
> findings, then port the firmware to the starter. Don't print my CPID or keys.

### Commands, OTA and twin

> Add a handler for the `pump_on` command with a parameter, and acknowledge success or failure.

> Implement OTA: download from the URLs, verify, apply, and acknowledge each step with the right statuses.

> Handle twin changes for my settings and report back only values the device applied.

### Gateway with child devices

> My gateway `gw1` has children with tags `pump` and `tank`. Using the skill's gateway starter, send
> telemetry for all of them in one message and acknowledge commands sent to children.

### Debugging

> My data isn't showing on the dashboard. Here's the template and the payload I send: ...

> SendData keeps returning None. Find out why.

> I get `AttributeError: ... has no attribute 'message'` when the SDK starts.

> A command from the platform stays pending.

### Before production

> Review `firmware/test0511.py` for production: debug off, TLS verification, no secrets in logs,
> offline storage size, git-ignored secrets.

---

## 6. What the skill makes the assistant do

So you know what to expect, and can spot when something was skipped:

- It asks for missing values and **never invents** IDs, keys or paths.
- It writes `iotc.env`, keeps `certs/` and `iotc.env` git-ignored, and does not repeat your CPID or keys in chat.
- It runs the **preflight** check itself and fixes what it can before connecting.
- The firmware it writes always:
  - registers command and OTA handlers and acknowledges what it does not handle as failed, even if
    the template defines no commands;
  - never sends faster than the template's data frequency (the starter enforces it);
  - sends values in the template's types (for example whole numbers for INTEGER);
  - waits until the SDK is ready before the first send;
  - reads all settings from `iotc.env`.
- It validates the payload against the template before you connect.

If a generated firmware is missing one of these, point the assistant at the skill's section
*"Every firmware must keep these"* and ask it to fix the code.

---

## 7. Using the scripts directly (no AI needed)

From the project folder (`S=.claude/skills/iotconnect-python-firmware/scripts`):

```bash
python $S/preflight.py --check-network              # checks everything; changes nothing; loads iotc.env
python $S/template_tool.py summary  template/MyTemplate.json
python $S/template_tool.py sample   template/MyTemplate.json      # a payload the SDK accepts
python $S/template_tool.py skeleton template/MyTemplate.json      # starter code for readings, commands, twin
python $S/template_tool.py validate template/MyTemplate.json payload.json
python $S/template_tool.py validate Gateway.json payload.json --device gw1=gw --device pump1=pump
python $S/import_sample_config.py old_firmware.py -o iotc.env   # settings from a sample-style file
```

- `validate` exits with 1 if any value would not arrive as normal telemetry, so it can gate a CI build.
- Firmware starters to copy: `assets/firmware_template.py` (one device) and
  `assets/gateway_firmware_template.py` (gateway with children).

---

## 8. Troubleshooting

| Symptom | What to do |
|---|---|
| The assistant says it doesn't have the skill | check the folder is `.claude/skills/iotconnect-python-firmware/SKILL.md` (or `.kiro/...`), then start a **new** session |
| Preflight: `iotconnect package importable` fails | install the SDK into the same Python the assistant uses: `pip install ./iotconnect-sdk-1.0` |
| Preflight: discovery request fails | check CPID, environment, platform and discovery URL; check network or proxy |
| Preflight: `env file git-ignored` or `device private key git-ignored` fails | add `iotc.env` and `certs/` to `.gitignore` |
| The device connects, then disconnects repeatedly | another program is connected **as the same device** (for example a second test run); stop it |
| `SendData` returns `None` | sending faster than the data frequency, before the SDK is ready, or a payload the SDK cannot process. Ask the assistant to validate the payload |
| Data arrives, but not as normal telemetry | key names or types differ from the template. Run `template_tool.py validate` |
| A command stays pending in the platform | the firmware did not acknowledge it; make sure the command handler is registered |

Deeper explanations are in the skill's `references/troubleshooting.md`.

---

## 9. Limits and notes

- The skill was checked against the SDK source in this repository (commit 8712097). Other SDK builds can
  differ. For example, some builds have no ARRAY type and no `UploadImage`/`GetCredentials`. If your
  installed SDK is a different build, ask the assistant to check the skill's rules against your SDK's code.
- The skill and its scripts never contact your device, and contact the platform only when you ask for the
  network check or run the firmware.
- Some details are not visible in the SDK code and are marked as unverified in the skill, for example the
  exact field names in platform-sent commands. Print the first message your firmware receives to confirm them.
- Known SDK issues the skill works around are listed in `skill-dev/SDK_ISSUES.md` in this repository.

---

## 10. Updating the skill

Replace the whole folder with the new version, then start a new session:

```bash
rm -rf .claude/skills/iotconnect-python-firmware
unzip iotconnect-python-firmware-v<N>.zip -d .claude/skills/
```

Do this for `.kiro/skills/` too if you use Kiro. Your `iotc.env`, `certs/`, `template/` and `firmware/` are
not inside the skill folder and are not touched.
