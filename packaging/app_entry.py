"""Packaged entry uses the same mandatory authentication and loopback launcher.

A console is intentional: pairing codes must never be put in URLs or log files.
No unsigned release is presented as a signed/notarized application.
"""
from beli_tool.cli import main

if __name__ == '__main__':
    main(['run'])
