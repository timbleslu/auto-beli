"""Single-use pairing, expiring sessions and strict same-origin mutations."""
from __future__ import annotations
import secrets
import threading
import time
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


class Sessions:
    def __init__(self, origin: str, pairing_code: str | None = None):
        p = urlsplit(origin)
        if (p.scheme not in ('http', 'https') or not p.hostname or p.path or p.query or p.fragment
            or p.username or p.password
            or (p.scheme == 'http' and p.hostname not in ('127.0.0.1', 'localhost', '[::1]', '::1'))):
            raise ValueError('Use a loopback HTTP origin or a trusted HTTPS origin')
        self.origin = origin
        self.host = p.netloc
        self.secure = p.scheme == 'https'
        self.cookie = '__Host-beli_session' if self.secure else 'beli_local_session'
        self.pairing_code = pairing_code or secrets.token_urlsafe(24)
        self.pairing_expires = time.monotonic() + 600
        self.sessions = {}
        self.attempts = []
        self.lock = threading.Lock()

    def same_origin(self, request: Request):
        if request.headers.get('origin') != self.origin:
            raise HTTPException(403, 'Same-origin request required')
        if request.headers.get('sec-fetch-site') not in (None, 'same-origin'):
            raise HTTPException(403, 'Cross-origin request rejected')
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise HTTPException(415, 'JSON required')

    def login(self, code):
        now = time.monotonic()
        with self.lock:
            self.attempts = [t for t in self.attempts if t > now - 60]
            if len(self.attempts) >= 5:
                raise HTTPException(429, 'Wait a minute before pairing again')
            self.attempts.append(now)
            if now > self.pairing_expires or not self.pairing_code or not secrets.compare_digest(code, self.pairing_code):
                raise HTTPException(403, 'Invalid or expired pairing code; restart for a new code')
            self.pairing_code = None
            value = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            self.sessions[value] = (now + 8 * 3600, csrf)
            return value, csrf

    def guard(self, request: Request):
        with self.lock:
            value = request.cookies.get(self.cookie, '')
            session = self.sessions.get(value)
            if not session or session[0] < time.monotonic():
                self.sessions.pop(value, None)
                raise HTTPException(401, 'Connect this browser first')
        if request.method not in ('GET', 'HEAD'):
            self.same_origin(request)
            if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), session[1]):
                raise HTTPException(403, 'Missing or invalid CSRF token')
        return session[1]
