"""Local pairing dialog: never put a pairing code in a URL or log."""
import socket
import subprocess
import time
import webbrowser


def pair_when_ready(origin: str, host: str, code: str):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, 8000), timeout=0.5):
                break
        except OSError:
            time.sleep(0.1)
    else:
        return
    script = '''on run argv
        display dialog (item 1 of argv) with title "Photos to Beli — connect browser" buttons {"Cancel", "Copy code"} default button "Copy code"
    end run'''
    text = f'Your one-time pairing code:\n{code}\n\nClick Copy code, then paste it into the assistant page at:\n{origin}\n\nThis code expires in 10 minutes.'
    result = subprocess.run(['osascript', '-e', script, text], capture_output=True, text=True)
    if result.returncode == 0 and 'Copy code' in result.stdout:
        subprocess.run(['pbcopy'], input=code, text=True, check=True)
        if host == '127.0.0.1':
            webbrowser.open(origin)
