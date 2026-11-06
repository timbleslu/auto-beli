import importlib.util
from pathlib import Path
import ssl
import socket
import threading
import time

import httpx
import uvicorn
from beli_tool.ledger import Ledger
from beli_tool.webapp import create_app
from test_webapp import _queue


def test_real_tls_transport_private_key_and_secure_pairing(tmp_path):
    spec=importlib.util.spec_from_file_location('make_phone_cert',Path(__file__).parents[1]/'tools/make_phone_cert.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    root=module.generate('192.168.1.2',tmp_path/'tls')
    assert (root/'server.key').stat().st_mode & 0o077==0
    # Connect to loopback, present the certified private LAN host/SNI explicitly.
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    origin=f'https://192.168.1.2:{port}'
    app=create_app(_queue(),Ledger(),origin=origin)
    config=uvicorn.Config(app,ssl_certfile=str(root/'server.crt'),ssl_keyfile=str(root/'server.key'),
                          proxy_headers=False,access_log=False,log_level='error')
    server=uvicorn.Server(config);thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    try:
        deadline=time.monotonic()+5
        while not server.started and time.monotonic()<deadline:time.sleep(.01)
        assert server.started
        context=ssl.create_default_context(cafile=str(root/'ca.crt'))
        with socket.create_connection(('127.0.0.1',port)) as raw:
            with context.wrap_socket(raw,server_hostname='192.168.1.2') as tls:
                assert tls.version() in ('TLSv1.2','TLSv1.3')
                tls.sendall(f'GET /api/queue HTTP/1.1\r\nHost: 192.168.1.2:{port}\r\nConnection: close\r\n\r\n'.encode())
                assert b'401 Unauthorized' in tls.recv(4096)
        # No warning bypass: a client lacking the CA rejects this certificate.
        with socket.create_connection(('127.0.0.1',port)) as raw:
            import pytest
            with pytest.raises(ssl.SSLCertVerificationError):
                ssl.create_default_context().wrap_socket(raw,server_hostname='192.168.1.2')
    finally:
        server.should_exit=True;thread.join(timeout=5);sock.close()
