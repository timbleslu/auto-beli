"""Read-only readiness checks. No Beli navigation until real controls are observed."""
from __future__ import annotations
import json
import shutil
import os
from pathlib import Path
import subprocess
import httpx


def doctor():
    env = os.environ.copy()
    xcode = Path('/Applications/Xcode.app/Contents/Developer')
    if xcode.is_dir():
        env.setdefault('DEVELOPER_DIR', str(xcode))
    for label, command in [
        ('macOS', ['sw_vers', '-productVersion']),
        ('Selected Apple developer tools', ['xcode-select', '-p']),
        ('Xcode', ['xcodebuild', '-version']),
        ('USB devices (local only; do not post device identifiers)', ['xcrun', 'devicectl', 'list', 'devices']),
    ]:
        print(label + ':')
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, env=env)
        print((result.stdout if result.returncode == 0 else 'Unavailable; finish Xcode setup first.').strip())
    print('Global Appium: ' + (shutil.which('appium') or 'not installed; use the locked local device-tools project'))
    try:
        response = httpx.get('http://127.0.0.1:4723/status', timeout=2, trust_env=False)
        response.raise_for_status()
        print('Loopback Appium status: reachable')
    except httpx.HTTPError:
        print('Loopback Appium status: not reachable')
    print('Beli navigation, ranking completion, iPhone photo availability, picker selection and saved uploads: UNVERIFIED')


def inspect_session(session_id: str):
    """Read accessibility source locally, without screenshots or outside AI.

    Only an already-created local session is inspected. Creating the Appium
    session, signing WDA and approving a real trial are separate physical steps.
    """
    if not session_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-' for c in session_id):
        raise ValueError('Invalid local Appium session identifier')
    with httpx.Client(base_url='http://127.0.0.1:4723', timeout=15, trust_env=False) as client:
        response = client.get(f'/session/{session_id}/source')
        response.raise_for_status()
        return response.json()['value']


def pilot_capabilities(*, udid: str, ios_version: str, bundle_id: str,
                       team: str, derived_data: str) -> dict:
    """Attach-only real-device pilot. Bundle identity must come from device inspection.

    No app archive, reinstall, reset, auto-launch, rating, picker or save command.
    WDA and its screenshot broadcaster bind to device loopback; forwarding is USB.
    """
    if not all((udid, ios_version, bundle_id, team, derived_data)):
        raise ValueError('Observed device, app and signing settings are required')
    return {'platformName': 'iOS', 'appium:automationName': 'XCUITest',
            'appium:udid': udid, 'appium:platformVersion': ios_version,
            'appium:bundleId': bundle_id, 'appium:noReset': True,
            'appium:fullReset': False, 'appium:autoLaunch': False,
            'appium:forceAppLaunch': False, 'appium:shouldTerminateApp': False,
            'appium:usePrebuiltWDA': True, 'appium:useNewWDA': False,
            'appium:derivedDataPath': derived_data,
            'appium:updatedWDABundleId': 'com.timbleslu.AutoBeliWDA',
            'appium:xcodeOrgId': team, 'appium:xcodeSigningId': 'Apple Development',
            'appium:wdaBindingIP': '127.0.0.1', 'appium:wdaLocalPort': 8100,
            'appium:skipLogCapture': True, 'appium:showXcodeLog': False,
            'appium:disableAutomaticScreenshots': True,
            'appium:newCommandTimeout': 3600,
            'appium:waitForIdleTimeout': 5}


def connected_usb_device(expected_udid=None):
    """Fresh, read-only USB observation; cached inventory is never connection proof.

    Returns private device metadata to the local caller. Do not log identifiers.
    """
    import tempfile
    env = os.environ.copy()
    developer = Path('/Applications/Xcode.app/Contents/Developer')
    if developer.is_dir():
        env['DEVELOPER_DIR'] = str(developer)
    with tempfile.TemporaryDirectory(prefix='auto-beli-device-') as folder:
        output = Path(folder) / 'devices.json'
        result = subprocess.run(['xcrun', 'devicectl', 'list', 'devices',
                                 '--json-output', str(output)],
                                capture_output=True, text=True, env=env, timeout=30)
        if result.returncode or not output.exists():
            raise RuntimeError('Xcode could not check the USB connection')
        devices = json.loads(output.read_text()).get('result', {}).get('devices', [])
    wired = [d for d in devices if d.get('connectionProperties', {}).get('transportType') == 'wired']
    if len(wired) != 1:
        raise RuntimeError('Connect and unlock exactly one iPhone over USB before starting')
    device = wired[0]
    udid = device.get('hardwareProperties', {}).get('udid')
    if not udid or (expected_udid is not None and udid != expected_udid):
        raise RuntimeError('The connected device does not match the configured trial iPhone')
    return device
