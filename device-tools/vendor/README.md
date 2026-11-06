# Reproducible, loopback-only XCUITest driver

Upstream: appium-xcuitest-driver 12.22.8, Apache-2.0 (LICENSE retained in archive).
Source tarball:
https://registry.npmjs.org/appium-xcuitest-driver/-/appium-xcuitest-driver-12.22.8.tgz

Verified upstream SHA512 (base64):
`aLZLEAXQe8HXiP197tmg/WvVPZ2T8DFnOQaq1wJi6NejMLdtS6FK2+LrmMJADNp0mXxxeCgYMntBIqQnwLuTqw==`

Output archive SHA256:
`6e2a5c240a148273ed38fd4cb16eceecc87a2f610589494f82c9ca9fab77cb7a`

The upstream package bundles nested dependency copies that ignore npm security overrides.
`tools/unbundle_driver.py` verifies the exact upstream checksum, removes bundled node_modules,
and removes bundleDependencies from its package manifest. It also changes the fallback USB
forwarder to listen on 127.0.0.1 instead of every interface, in both TypeScript source and its
compiled JavaScript. These two exact replacements are checked against the checksum-verified
upstream archive; unexpected source fails the recipe. The other 740 files are unchanged.
The resulting archive is deterministic; tests also inspect the real fallback socket binding.

The local file dependency lets package-lock.json and glob/minimatch overrides cover the entire
tree. No source recompilation is needed: the two-line forwarding fix is applied to source and compiled code. Keep the tarball in Git so
`npm ci --ignore-scripts` works from a fresh clone. npm also verifies its locked integrity hash.

To reproduce from the repository root:

```sh
curl --fail --proto '=https' https://registry.npmjs.org/appium-xcuitest-driver/-/appium-xcuitest-driver-12.22.8.tgz -o /tmp/xcuitest-upstream.tgz
python3 tools/unbundle_driver.py /tmp/xcuitest-upstream.tgz /tmp/xcuitest-unbundled.tgz
shasum -a 256 /tmp/xcuitest-unbundled.tgz
```

Never bypass TLS verification to fetch upstream packages. This pinned package and audit
provide reproducibility and known-advisory coverage, not proof that all upstream code is safe.
