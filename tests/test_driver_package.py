import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).parents[1]


def test_vendored_driver_is_unbundled_and_keeps_license():
    path=ROOT/'device-tools/vendor/appium-xcuitest-driver-12.22.8-loopback.tgz'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '6e2a5c240a148273ed38fd4cb16eceecc87a2f610589494f82c9ca9fab77cb7a'
    with tarfile.open(path) as archive:
        names=archive.getnames()
        assert not any('node_modules' in n.split('/') for n in names)
        for code in ('package/lib/device/device-connections-factory.ts', 'package/build/lib/device/device-connections-factory.js'):
            assert b'this.localServer.listen(this.localport, LOCALHOST);' in archive.extractfile(code).read()
        assert 'package/LICENSE' in names
        assert 'package/build/lib/index.js' in names
        package=json.load(archive.extractfile('package/package.json'))
        assert package['name']=='appium-xcuitest-driver'
        assert package['version']=='12.22.8'
        assert 'bundleDependencies' not in package
        assert 'bundledDependencies' not in package


def test_wrong_upstream_checksum_is_rejected(tmp_path):
    spec=importlib.util.spec_from_file_location('unbundle',ROOT/'tools/unbundle_driver.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source=tmp_path/'fake.tgz';source.write_bytes(b'not the upstream driver')
    import pytest
    with pytest.raises(ValueError,match='checksum mismatch'):
        module.repackage(source,tmp_path/'out.tgz')
    assert not (tmp_path/'out.tgz').exists()
