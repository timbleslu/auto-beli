# Local USB tooling — pilot only

Pinned: Appium 3.9.0, XCUITest driver 12.22.8, Node >=26, npm >=10.
The latest driver major found during setup (13.0.7) requires Appium 4 beta;
it was not installed as an incompatible pair with stable Appium 3.

From this directory, `npm ci --ignore-scripts` restores package-lock.json.
Read ../SECURITY.md and vendor/README.md for provenance of the unbundled driver.
Dependency bundling was removed so the locked security overrides apply everywhere;
a two-line fallback-forwarder patch enforces loopback binding in source and compiled JavaScript. A clean reinstall and npm audit reported zero known vulnerabilities.

The assistant registered the pinned driver locally using:

```sh
APPIUM_HOME="$PWD/private/appium" ./node_modules/.bin/appium driver install --source=local "$PWD/node_modules/appium-xcuitest-driver"
```

Do not rerun installation blindly if already registered. To check:

```sh
APPIUM_HOME="$PWD/private/appium" ./node_modules/.bin/appium driver list --installed
```

No phone session, helper signing or Beli navigation is automatic. After preparing and verifying WDA with the assistant,
the local-only server command is:

```sh
umask 077
APPIUM_HOME="$PWD/private/appium" DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer ./node_modules/.bin/appium --address 127.0.0.1 --port 4723 --log-level warn
```

Do not use relaxed security, network bind addresses, session overrides, tunnels,
or app reinstall/reset capabilities. Keep captures and session settings inside
ignored private/. Logs and accessibility source can contain private account data.
Do not upload those files. No real-device success is claimed by installing these tools.
