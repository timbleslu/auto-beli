from beli_tool.device import pilot_capabilities


def test_pilot_is_attach_only_and_wda_is_loopback():
    caps=pilot_capabilities(udid='synthetic',ios_version='27.0.1',bundle_id='synthetic.app',team='SYNTHETIC',derived_data='/tmp/synthetic-build')
    assert caps['appium:autoLaunch'] is False
    assert caps['appium:noReset'] is True
    assert caps['appium:fullReset'] is False
    assert caps['appium:forceAppLaunch'] is False
    assert caps['appium:shouldTerminateApp'] is False
    assert caps['appium:usePrebuiltWDA'] is True
    assert caps['appium:wdaBindingIP']=='127.0.0.1'
    assert 'appium:app' not in caps


def test_live_usb_probe_rejects_disconnected_or_wrong_phone(monkeypatch):
    import json
    from pathlib import Path
    from types import SimpleNamespace
    import pytest
    from beli_tool.device import connected_usb_device
    devices=[]
    def run(args,**kwargs):
        output=Path(args[args.index('--json-output')+1])
        output.write_text(json.dumps({'result':{'devices':devices}}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr('beli_tool.device.subprocess.run',run)
    with pytest.raises(RuntimeError,match='USB'):connected_usb_device('synthetic-target')
    devices.append({'hardwareProperties':{'udid':'synthetic-target'},'connectionProperties':{'transportType':'network'}})
    with pytest.raises(RuntimeError,match='USB'):connected_usb_device('synthetic-target')
    devices[0]['connectionProperties']['transportType']='wired'
    with pytest.raises(RuntimeError,match='configured trial'):connected_usb_device('different-device')
    assert connected_usb_device('synthetic-target')['hardwareProperties']['udid']=='synthetic-target'
