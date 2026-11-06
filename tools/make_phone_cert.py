#!/usr/bin/env python3
"""Create a dedicated private CA and TLS server certificate. Does not install trust.

Usage: python3 tools/make_phone_cert.py MAC_LAN_IP PRIVATE_OUTPUT_DIRECTORY
The iPhone must explicitly trust ca.crt before phone access is used.
Never transfer ca.key or server.key.
"""
import ipaddress
import os
from pathlib import Path
import subprocess
import sys


def generate(ip, directory):
    address = ipaddress.ip_address(ip)
    if address.version != 4 or not address.is_private or address.is_loopback or address.is_unspecified:
        raise ValueError('Use the Mac’s private LAN IPv4 address')
    os.umask(0o077)
    root = Path(directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    config = root / 'openssl.cnf'
    config.write_text(f'''[req]
distinguished_name=dn
prompt=no
[dn]
CN=Auto Beli private trial CA
[ca_ext]
basicConstraints=critical,CA:TRUE,pathlen:0
keyUsage=critical,keyCertSign,cRLSign
subjectKeyIdentifier=hash
[server_ext]
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:{address}
authorityKeyIdentifier=keyid,issuer
''')
    def run(*args):
        subprocess.run(['/usr/bin/openssl', *args], cwd=root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    run('req','-x509','-newkey','rsa:3072','-nodes','-sha256','-days','30',
        '-keyout','ca.key','-out','ca.crt','-config','openssl.cnf','-extensions','ca_ext')
    run('req','-new','-newkey','rsa:3072','-nodes','-sha256','-keyout','server.key',
        '-out','server.csr','-subj',f'/CN={address}')
    run('x509','-req','-in','server.csr','-CA','ca.crt','-CAkey','ca.key',
        '-CAcreateserial','-out','server.crt','-days','14','-sha256',
        '-extfile','openssl.cnf','-extensions','server_ext')
    run('verify','-CAfile','ca.crt','server.crt')
    print(f'Certificates created in {root}. No device trust settings were changed.')
    print('Transfer only ca.crt to the iPhone. Keep BOTH .key files private on the Mac.')
    return root

if __name__ == '__main__':
    if len(sys.argv)!=3:
        raise SystemExit(__doc__)
    generate(sys.argv[1],sys.argv[2])
