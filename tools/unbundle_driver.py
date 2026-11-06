#!/usr/bin/env python3
"""Repackage the checksum-verified upstream driver without bundled dependencies.

Two explicit loopback-binding fixes. Removing bundled node_modules lets npm's locked dependency
resolution and security overrides apply to every copy. Archive output is deterministic.
"""
import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

UPSTREAM_URL = 'https://registry.npmjs.org/appium-xcuitest-driver/-/appium-xcuitest-driver-12.22.8.tgz'
UPSTREAM_SHA512 = 'aLZLEAXQe8HXiP197tmg/WvVPZ2T8DFnOQaq1wJi6NejMLdtS6FK2+LrmMJADNp0mXxxeCgYMntBIqQnwLuTqw=='


def repackage(upstream: Path, output: Path):
    data = upstream.read_bytes()
    if base64.b64encode(hashlib.sha512(data).digest()).decode() != UPSTREAM_SHA512:
        raise ValueError('Upstream package checksum mismatch; refusing to repackage')
    retained = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for entry in archive.getmembers():
            path = PurePosixPath(entry.name)
            if path.is_absolute() or '..' in path.parts or path.parts[0] != 'package':
                raise ValueError('Unexpected archive path')
            if 'node_modules' in path.parts or entry.isdir():
                continue
            if not entry.isfile():
                raise ValueError('Unexpected non-file in unbundled driver')
            body = archive.extractfile(entry).read()
            if entry.name in ('package/lib/device/device-connections-factory.ts',
                               'package/build/lib/device/device-connections-factory.js'):
                old = b'this.localServer.listen(this.localport);'
                if body.count(old) != 1:
                    raise ValueError('Upstream fallback forwarding code changed')
                body = body.replace(old, b'this.localServer.listen(this.localport, LOCALHOST);')
            if entry.name == 'package/package.json':
                package = json.loads(body)
                if package['name'] != 'appium-xcuitest-driver' or package['version'] != '12.22.8':
                    raise ValueError('Unexpected upstream package')
                package.pop('bundleDependencies', None)
                package.pop('bundledDependencies', None)
                body = (json.dumps(package, indent=2) + '\n').encode()
            retained[entry.name] = (body, entry.mode)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('wb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as archive:
                for name, (body, mode) in sorted(retained.items()):
                    entry = tarfile.TarInfo(name)
                    entry.size = len(body); entry.mode = mode
                    entry.uid = entry.gid = entry.mtime = 0
                    archive.addfile(entry, io.BytesIO(body))
    return hashlib.sha256(output.read_bytes()).hexdigest()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(repackage(args.upstream, args.output))
