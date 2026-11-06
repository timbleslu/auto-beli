import assert from 'node:assert/strict';
import net from 'node:net';
import test from 'node:test';
import {DeviceConnectionsFactory} from './node_modules/appium-xcuitest-driver/build/lib/device/device-connections-factory.js';

test('legacy USB forwarding listens only on loopback, without contacting a device', async () => {
  const probe = net.createServer();
  await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve));
  const port = probe.address().port;
  await new Promise(resolve => probe.close(resolve));
  const log = new Proxy({}, {get: () => () => {}});
  const factory = new DeviceConnectionsFactory(log);
  try {
    await factory.requestConnection('synthetic-device', port, {usePortForwarding:true, devicePort:8100});
    // Inspect the actual bound socket. No client connects and no USB command runs.
    const mapping = Object.values(DeviceConnectionsFactory._connectionsMapping)[0];
    assert.equal(mapping.portForwarder.localServer.address().address, '127.0.0.1');
  } finally {
    await factory.releaseConnection('synthetic-device', port);
  }
});
