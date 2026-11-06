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
