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
from beli_tool.saved_places import SavedPlace, SavedPlaces, match_saved_selection
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
    photos: list[str] = Field(max_length=100)

class Batch(Strict):
    mappings: list[Mapping] = Field(max_length=20)

class DiscoverReq(Strict):
    photos: list[str] = Field(min_length=1, max_length=100)
    query: str = Field(default='', max_length=200)
    radius_m: int = Field(default=1000)
    include_external: bool = False

class SavedBatch(Strict):
    entries: list[SavedPlace] = Field(min_length=1, max_length=500)

class UserRestaurantReq(Strict):
    photos: list[str] = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=500)

class RemoveReq(Strict):
    visit_id: str = Field(max_length=64)

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
            'photos': _refs(item), 'status': item.status, 'match_note': item.match_note,
            'venue_hints':item.raw.venue_hints, 'city_hint':item.raw.city_hint,
            'candidates': [c.model_dump() for c in ([item.match] if item.match else item.candidates)]}


def create_app(queue: Queue, ledger, photo_resolver=None, token=None, rebuild=None,
               obsidian_log=None, origin='http://127.0.0.1:8000', discovery=None, match_photos=None, window=None, max_groups=3) -> FastAPI:
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
    saved_places = SavedPlaces(ledger)
    def selected_queue():
        matches = work.matches()
        if window:
            matches = [m for m in matches if m.raw.visit_date and window[0] <= m.raw.visit_date <= window[1]]
        return Queue(been=[m for m in matches if m.status != 'no_match'],
                     review=[m for m in matches if m.status == 'no_match'])
    state = {'queue': selected_queue() if discovery else queue}
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
                'discovery_enabled': discovery is not None,
                'visits': [{**_serialize(m),
                            'legacy_record': bool(m.match and ledger.is_handled(m.match.place_id))}
                           for m in _items(state['queue'])]}

    @app.get('/api/photo/{uuid}')
    def photo(uuid: str, csrf=Depends(sessions.guard)):
        allowed = {r for m in _items(state['queue']) for r in _refs(m)}
        allowed.update(r for v in work.snapshot()['visits'] for r in v['photos'])
        if discovery:
            allowed.update(a.id for a in discovery())
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

    @app.get('/api/discovery')
    def inventory(csrf=Depends(sessions.guard)):
        if not discovery:
            raise HTTPException(404)
        assets = discovery()
        return {'photos':[a.public() for a in assets],
                'since':str(window[0]) if window else '', 'until':str(window[1]) if window else '',
                'max_groups':max_groups,
                'saved_places':saved_places.summary(),
                'likely_food':sum(a.food for a in assets),
                'without_gps':sum(a.lat is None or a.lon is None for a in assets)}

    @app.get('/api/saved-places')
    def saved_list(csrf=Depends(sessions.guard)):
        return {**saved_places.summary(), 'entries':[e.model_dump() for e in saved_places.entries()]}

    @app.post('/api/saved-places')
    def save_list(req: SavedBatch, csrf=Depends(sessions.guard)):
        # Local ingestion seam for a later observed phone-list capture. This does
        # not assert live sync, verified identity, visit or photo approval.
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'Another matching operation is running')
        try:
            if work.snapshot()['status'] == 'running':
                raise HTTPException(409, 'Pause before updating your saved shortlist')
            saved_places.upsert(req.entries)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        finally:
            lock.release()
        return saved_places.summary()

    def update_group(photos, make_match):
        if discovery is None:
            raise HTTPException(404)
        if work.snapshot()['status'] == 'running':
            raise HTTPException(409, 'Pause before reviewing a new photo group')
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'Another matching operation is running')
        try:
            # Validate selection before an external request, including membership.
            known = {a.id for a in discovery()}
            if not set(photos) <= known:
                raise ValueError('Selected photos are outside the current date window')
            done = {v['visit_id'] for v in work.snapshot()['visits'] if v['outcome'] != 'pending'}
            groups = [m for m in _items(state['queue']) if visit_id(m) not in done]
            same_group = any(set(_refs(m)) == set(photos) for m in groups)
            if len(groups) >= max_groups and not same_group:
                raise ValueError('Finish or return a group to discovery before adding more trial visits')
            item = make_match()
            work.save_match(item)
            state['queue'] = selected_queue()
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        except PlacesError as e:
            raise HTTPException(502, 'OSM search unavailable. Your photo selection stays pending; try again later.') from e
        finally:
            lock.release()
        return {'ok':True}

    @app.post('/api/discovery-match')
    def discover_match(req: DiscoverReq, csrf=Depends(sessions.guard)):
        if match_photos is None:
            raise HTTPException(404)
        if req.radius_m not in (250, 500, 1000, 2000):
            raise HTTPException(422, 'Choose a search distance of 250, 500, 1000 or 2000 metres')
        def find():
            entries = saved_places.entries()
            if not entries:
                item = match_photos(req.photos, req.query)
                item.match_note = 'Your Beli shortlist is not loaded yet; these are external-provider suggestions. ' + (item.match_note or '')
                return item
            local = match_saved_selection(discovery(), req.photos, entries, req.query, req.radius_m)
            if req.include_external:
                try:
                    external = match_photos(req.photos, req.query)
                except (PlacesError, ValueError):
                    # A provider outage/missing GPS must not discard saved matches.
                    local.match_note = local.match_note.replace('No external lookup was made.',
                        'External suggestions were requested but unavailable; saved-list results retained.')
                    return local
                # Catalog and provider identities intentionally remain distinct.
                local.candidates.extend(external.candidates or ([external.match] if external.match else []))
                local.status = 'ambiguous' if local.candidates else 'no_match'
                local.match_note = local.match_note.replace('No external lookup was made.',
                    'You requested extra external-provider suggestions; visit hints/GPS may have been sent.')
            return local
        return update_group(req.photos, find)

    @app.post('/api/user-restaurant')
    def supplied_restaurant(req: UserRestaurantReq, csrf=Depends(sessions.guard)):
        from beli_tool.discovery import user_restaurant
        return update_group(req.photos,
            lambda: user_restaurant(discovery(), req.photos, req.name, req.address))

    @app.post('/api/remove-match')
    def remove_match(req: RemoveReq, csrf=Depends(sessions.guard)):
        if not discovery or work.snapshot()['status'] == 'running':
            raise HTTPException(409, 'Pause before editing unapproved groups')
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'Another matching operation is running')
        try:
            work.remove_match(req.visit_id)
            state['queue'] = selected_queue()
        except ValueError as e:
            raise HTTPException(409,str(e)) from e
        finally:
            lock.release()
        return {'ok':True}

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
                             'candidate_source':candidate.candidate_source,
                             'saved_list_status':candidate.saved_list_status,
                             'observed_beli_id':candidate.beli_id,
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
