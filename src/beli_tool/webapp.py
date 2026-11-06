from __future__ import annotations

import threading
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from beli_tool import __version__
from beli_tool.pipeline import Queue
from beli_tool.places_client import PlacesError
from beli_tool.security import Sessions
from beli_tool.worklist import Worklist, visit_id

_ROOT = Path(__file__).parent
_INDEX = (_ROOT / 'templates/index.html').read_text()
_CSP = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; object-src 'none'"


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Login(Strict):
    code: str = Field(max_length=256)

class Mapping(Strict):
    visit_id: str = Field(max_length=64)
    provider_id: str = Field(max_length=256)
    photos: list[str] = Field(max_length=6)

class Batch(Strict):
    mappings: list[Mapping] = Field(max_length=20)

class Control(Strict):
    action: str

class Manual(Strict):
    visit_id: str
    action: str
    photo: str | None = None
    name: str | None = None
    address: str | None = None


def _items(queue):
    return queue.want_to_try + queue.been + queue.review


def _refs(item):
    return item.raw.photo_refs or ([item.raw.photo_ref] if item.raw.photo_ref else [])


def _serialize(item):
    return {'visit_id': visit_id(item), 'source': item.raw.source,
            'name': item.match.name if item.match else item.raw.name,
            'visit_date': str(item.raw.visit_date or ''),
            'photos': _refs(item), 'status': item.status,
            'candidates': [c.model_dump() for c in ([item.match] if item.match else item.candidates)]}


def create_app(queue: Queue, ledger, photo_resolver=None, token=None, rebuild=None,
               obsidian_log=None, origin='http://127.0.0.1:8000') -> FastAPI:
    """Auth is mandatory, even with token=None. token is an optional pairing seed.

    Only the public shell/static assets/login are unauthenticated. Private assets
    must be members of the current queue or approved worklist. Legacy /added is
    deliberately retired: a local ledger row cannot verify a Beli save.
    """
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    sessions = Sessions(origin, token)
    app.state.pairing_code = sessions.pairing_code
    app.state.sessions = sessions
    work = Worklist(ledger)
    state = {'queue': queue}
    lock = threading.Lock()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[sessions.host.split(':')[0]])

    @app.middleware('http')
    async def headers(request, call_next):
        # Uvicorn proxy headers are disabled by both launchers. Never trust
        # a LAN client's spoofed X-Forwarded-Proto or Host.
        if request.headers.get('host') != sessions.host:
            return Response(status_code=400)
        if request.url.scheme != ('https' if sessions.secure else 'http'):
            return Response(status_code=400)
        response = await call_next(request)
        response.headers.update({'Content-Security-Policy': _CSP,
                                 'X-Content-Type-Options': 'nosniff',
                                 'Referrer-Policy': 'no-referrer',
                                 'Cache-Control': 'no-store',
                                 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()'})
        if sessions.secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @app.get('/', response_class=HTMLResponse)
    def index():
        return HTMLResponse(_INDEX)

    @app.get('/static/{filename}')
    def static(filename: str):
        if filename not in ('app.js', 'app.css'):
            raise HTTPException(404)
        return FileResponse(_ROOT / 'static' / filename)

    @app.post('/api/login')
    def login(req: Login, request: Request):
        sessions.same_origin(request)
        value, csrf = sessions.login(req.code)
        response = Response(content='{"ok":true}', media_type='application/json')
        response.set_cookie(sessions.cookie, value, max_age=28800,
                            secure=sessions.secure, httponly=True, samesite='strict', path='/')
        return response

    @app.get('/api/session')
    def session(csrf=Depends(sessions.guard)):
        return {**work.snapshot(), 'csrf': csrf}

    @app.post('/api/logout')
    def logout(request: Request, csrf=Depends(sessions.guard)):
        with sessions.lock:
            sessions.sessions.pop(request.cookies.get(sessions.cookie), None)
        response = Response(content='{"ok":true}', media_type='application/json')
        response.delete_cookie(sessions.cookie, secure=sessions.secure, httponly=True, samesite='strict')
        return response

    @app.get('/api/queue')
    def get_queue(csrf=Depends(sessions.guard)):
        # Do not hide ambiguous visits because another candidate was handled.
        # Legacy records are visible for explicit reconciliation, never promoted
        # to machine verification and never used as new Beli identities.
        return {'version': __version__, 'can_rescan': rebuild is not None,
                'visits': [{**_serialize(m),
                            'legacy_record': bool(m.match and ledger.is_handled(m.match.place_id))}
                           for m in _items(state['queue'])]}

    @app.get('/api/photo/{uuid}')
    def photo(uuid: str, csrf=Depends(sessions.guard)):
        allowed = {r for m in _items(state['queue']) for r in _refs(m)}
        allowed.update(r for v in work.snapshot()['visits'] for r in v['photos'])
        if uuid not in allowed:
            raise HTTPException(404)
        path = photo_resolver(uuid) if photo_resolver else None
        if not path:
            raise HTTPException(404)
        path = Path(path)
        types = {'.jpg': ('image/jpeg', b'\xff\xd8\xff'),
                 '.jpeg': ('image/jpeg', b'\xff\xd8\xff'),
                 '.png': ('image/png', b'\x89PNG\r\n\x1a\n')}
        media = types.get(path.suffix.lower())
        if not media or not path.is_file():
            raise HTTPException(404, 'Preview unavailable; check the original in Photos')
        with path.open('rb') as f:
            if not f.read(8).startswith(media[1]):
                raise HTTPException(404)
        return FileResponse(path, media_type=media[0])

    @app.post('/api/approve')
    def approve(req: Batch, csrf=Depends(sessions.guard)):
        by_id = {visit_id(m): m for m in _items(state['queue'])}
        mappings = []
        for selection in req.mappings:
            m = by_id.get(selection.visit_id)
            if not m:
                raise HTTPException(409, 'Visit changed; rescan and review again')
            candidates = [m.match] if m.match else m.candidates
            candidate = next((c for c in candidates if c.place_id == selection.provider_id), None)
            if not candidate or len(set(selection.photos)) != len(selection.photos) or not set(selection.photos) <= set(_refs(m)):
                raise HTTPException(400, 'Approve only suggested restaurant and photo mappings')
            mappings.append({'visit_id': selection.visit_id, 'provider_id': candidate.place_id,
                             'name': candidate.name, 'address': candidate.address,
                             'source': m.raw.source, 'visit_date': str(m.raw.visit_date or ''),
                             'photos': selection.photos})
        try:
            work.approve(mappings)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return {'ok': True}

    @app.post('/api/control')
    def control(req: Control, csrf=Depends(sessions.guard)):
        try:
            work.control(req.action)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return {'ok': True}

    @app.post('/api/manual')
    def manual(req: Manual, csrf=Depends(sessions.guard)):
        try:
            work.manual(req.visit_id, req.action, req.photo, req.name, req.address)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return {'ok': True}

    @app.post('/api/rescan')
    def rescan(csrf=Depends(sessions.guard)):
        if rebuild is None:
            raise HTTPException(501, 'Rescan unavailable')
        if work.snapshot()['status'] == 'running':
            raise HTTPException(409, 'Pause before rescanning')
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'A rescan is already running')
        try:
            state['queue'] = rebuild()
        except PlacesError as e:
            # Providers may include request details/coordinates in errors.
            raise HTTPException(502, 'Matching failed. Try again later; private provider details were not logged.') from e
        finally:
            lock.release()
        return {'ok': True}

    return app
