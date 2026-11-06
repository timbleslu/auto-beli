from datetime import date
from fastapi.testclient import TestClient
import pytest

from beli_tool.models import MatchedPlace, PlaceCandidate, RawPlace
from beli_tool.pipeline import Queue
from beli_tool.ledger import Ledger
from beli_tool.webapp import create_app

ORIGIN = 'http://127.0.0.1:8000'


def _queue(name='Lilia', ident='osm:node/1'):
    return Queue(been=[MatchedPlace(bucket='been', status='confident',
        raw=RawPlace(source='photos', lat=40.7, lon=-73.9, visit_date=date(2026,4,12),
                     photo_count=2,photo_ref='photo1',photo_refs=['photo1','photo2']),
        match=PlaceCandidate(place_id=ident,name=name,address='567 Union Ave',category='restaurant'))])


def connect(app, origin=ORIGIN):
    client = TestClient(app, base_url=origin)
    assert client.post('/api/login',json={'code':app.state.pairing_code},headers={'Origin':origin}).status_code == 200
    csrf=client.get('/api/session').json()['csrf']
    client.headers.update({'Origin':origin,'X-CSRF-Token':csrf})
    return client


def approved(client, photos=None):
    visit=client.get('/api/queue').json()['visits'][0]
    mapping={'visit_id':visit['visit_id'],'provider_id':visit['candidates'][0]['place_id'],'photos':photos if photos is not None else ['photo1']}
    assert client.post('/api/approve',json={'mappings':[mapping]}).status_code == 200
    return mapping


def test_auth_is_mandatory_and_query_credentials_are_rejected():
    app=create_app(_queue(),Ledger())
    c=TestClient(app,base_url=ORIGIN)
    for route in ('/api/queue','/api/session','/api/photo/photo1'):
        assert c.get(route,params={'t':app.state.pairing_code}).status_code == 401
    assert c.post('/api/control',json={'action':'start'}).status_code==401
    assert c.get('/docs').status_code == 404
    assert c.get('/openapi.json').status_code == 404
    assert c.get('/').status_code == 200
    assert app.state.pairing_code not in c.get('/').text


def test_pairing_is_single_use_expiring_and_rate_limited():
    app=create_app(_queue(),Ledger()); code=app.state.pairing_code
    c=connect(app)
    assert c.post('/api/login',json={'code':code}).status_code==403
    expired=create_app(_queue(),Ledger()); expired.state.sessions.pairing_expires=0
    raw=TestClient(expired,base_url=ORIGIN)
    for _ in range(5):
        assert raw.post('/api/login',json={'code':expired.state.pairing_code},headers={'Origin':ORIGIN}).status_code==403
    assert raw.post('/api/login',json={'code':'bad'},headers={'Origin':ORIGIN}).status_code==429


def test_session_expiry_and_logout():
    app=create_app(_queue(),Ledger()); c=connect(app)
    key=c.cookies.get('beli_local_session')
    app.state.sessions.sessions[key]=(0,'old')
    assert c.get('/api/queue').status_code==401
    app=create_app(_queue(),Ledger()); c=connect(app)
    assert c.post('/api/logout',json={}).status_code==200
    assert c.get('/api/queue').status_code==401


def test_tls_cookies_headers_and_origin_validation():
    app=create_app(_queue(),Ledger(),origin='https://192.168.1.2:8000')
    c=connect(app,'https://192.168.1.2:8000')
    cookie=c.cookies.get('__Host-beli_session')
    assert cookie
    r=c.get('/')
    assert "script-src 'self'" in r.headers['content-security-policy']
    assert 'unsafe-inline' not in r.headers['content-security-policy']
    assert r.headers['cache-control']=='no-store'
    assert r.headers['referrer-policy']=='no-referrer'
    assert 'strict-transport-security' in r.headers
    assert c.get('/api/queue',headers={'Host':'evil.test'}).status_code==400
    with pytest.raises(ValueError): create_app(_queue(),Ledger(),origin='http://192.168.1.2:8000')


def test_csrf_and_login_cross_origin_protection():
    app=create_app(_queue(),Ledger()); c=connect(app)
    for headers in ({'Origin':'https://evil.test'}, {'X-CSRF-Token':'wrong'}, {'Sec-Fetch-Site':'cross-site'}):
        assert c.post('/api/control',json={'action':'stop'},headers=headers).status_code==403
    assert c.post('/api/control',content='action=stop',headers={'Content-Type':'application/x-www-form-urlencoded'}).status_code==415
    raw=TestClient(create_app(_queue(),Ledger()),base_url=ORIGIN)
    assert raw.post('/api/login',json={'code':'test'},headers={'Origin':'https://evil.test'}).status_code==403


def test_photos_allowlist_and_content_type(tmp_path):
    png=tmp_path/'photo.png'; png.write_bytes(b'\x89PNG\r\n\x1a\nsynthetic')
    seen=[]
    def resolver(ref):
        seen.append(ref); return png
    c=connect(create_app(_queue(),Ledger(),photo_resolver=resolver))
    assert c.get('/api/photo/photo1').status_code==200
    assert c.get('/api/photo/unapproved').status_code==404
    assert seen==['photo1']
    png.write_text('<script>alert(1)</script>')
    assert c.get('/api/photo/photo1').status_code==404


def test_batch_is_validated_and_atomic():
    c=connect(create_app(_queue(),Ledger()))
    m=approved(c)
    assert c.post('/api/approve',json={'mappings':[m]}).status_code==200
    assert len(c.get('/api/session').json()['visits'])==1
    for changed in ({'photos':['private']},{'provider_id':'unrelated'},{'photos':['photo1','photo1']}):
        assert c.post('/api/approve',json={'mappings':[{**m,**changed}]}).status_code==400
    assert c.post('/api/approve',json={'mappings':[{**m,'photos':[]}]}).status_code==409
    assert c.post('/api/approve',json={'mappings':[m,m]}).status_code==409
    assert c.get('/api/session').json()['visits'][0]['photos']==['photo1']


def test_manual_flow_does_not_claim_machine_verification():
    led=Ledger(); c=connect(create_app(_queue(),led)); m=approved(c)
    body={'visit_id':m['visit_id']}
    def action(a,**kw): return c.post('/api/manual',json={**body,'action':a,**kw})
    assert action('ranking').status_code==409
    assert c.post('/api/control',json={'action':'start'}).status_code==200
    assert action('ranking').status_code==409
    assert action('identity',name='Wrong branch',address='567 Union Ave').status_code==409
    assert action('identity',name='Lilia',address='567 Union Ave').status_code==200
    assert action('ranking').status_code==200
    assert action('finish').status_code==409
    assert action('photo',photo='unapproved').status_code==409
    assert action('photo',photo='photo1').status_code==200
    assert action('finish').status_code==200
    state=c.get('/api/session').json()
    assert state['automation_verified'] is False
    assert state['visits'][0]['outcome']=='user_finished'
    assert state['visits'][0]['ranking']=='user_confirmed'
    assert not led.handled_ids()  # don't pollute legacy or assert a Beli save
    assert c.post('/api/added',json={}).status_code==404


def test_rescan_guard_and_failure_recovery():
    from beli_tool.places_client import PlacesError
    calls=[]
    def rebuild():
        calls.append(1)
        if len(calls)==1: raise PlacesError('private coordinate or key')
        return Queue()
    c=connect(create_app(_queue(),Ledger(),rebuild=rebuild)); approved(c)
    c.post('/api/control',json={'action':'start'})
    assert c.post('/api/rescan',json={}).status_code==409
    c.post('/api/control',json={'action':'pause'})
    failure=c.post('/api/rescan',json={})
    assert failure.status_code==502 and 'private coordinate' not in failure.text
    assert c.post('/api/rescan',json={}).status_code==200


def test_legacy_handled_candidate_remains_visible():
    led=Ledger(); led.mark_added('osm:node/1','Lilia','been')
    c=connect(create_app(_queue(),led))
    assert c.get('/api/queue').json()['visits'][0]['legacy_record']
