from dataclasses import replace
from datetime import datetime, timedelta
import sqlite3

import pytest
from fastapi.testclient import TestClient

from beli_tool.discovery import PhotoAsset
from beli_tool.ledger import Ledger
from beli_tool.saved_places import SavedPlace, SavedPlaces, match_saved_selection
from beli_tool.worklist import Worklist, visit_id
from test_discovery import Provider, discovery_app
from test_webapp import connect


def photo(**kwargs):
    return replace(PhotoAsset('a', datetime(2026,10,24,12), 40,-73,True,True,False), **kwargs)


def branch(**kwargs):
    return SavedPlace.model_validate({'name':'Café Élan', 'address':'1 Test St, Test City',
        'lat':40.006, 'lon':-73, 'location_source':'beli_ui', 'list_status':'want_to_try', **kwargs})


def test_wider_shortlist_search_preserves_branches_and_never_accepts_visit():
    entries = [branch(),branch(address='2 Test St, Test City',lat=40.008,list_status='been')]
    assert match_saved_selection([photo()],['a'],entries,radius_m=500).status == 'no_match'
    result=match_saved_selection([photo()],['a'],entries,radius_m=1000)
    assert result.status=='ambiguous' and result.match is None
    assert len(result.candidates)==2
    assert len({c.place_id for c in result.candidates})==2
    assert all(c.place_id.startswith('beli_saved:') and c.beli_id is None for c in result.candidates)
    assert result.candidates[1].saved_list_status=='been'
    assert 'existing ranking' in ' '.join(result.candidates[1].evidence)


def test_local_name_agreement_ranks_before_nearest_restaurant():
    result=match_saved_selection([photo(venue_hints=('Cafe\u0301 E\u0301lan',))], ['a'],
        [branch(name='Closer but unrelated',lat=40.0001),branch()])
    assert result.candidates[0].name=='Café Élan'
    assert 'hint' in ' '.join(result.candidates[0].evidence)


def test_explicit_query_can_correct_city_outside_radius_without_provider_lookup():
    result=match_saved_selection([photo(city_hint='Wrong City')],['a'],
        [branch(lat=41,address='4 Test St, Correct City')],query='Correct City')
    assert len(result.candidates)==1
    assert result.candidates[0].distance_m>1000
    assert 'outside' in ' '.join(result.candidates[0].evidence)
    assert match_saved_selection([photo()],['a'],[branch()],query='Cafe Elan, Test City').candidates
    assert not match_saved_selection([photo()],['a'],[branch()],query='!!!').candidates


def test_missing_gps_does_not_offer_entire_catalog_and_missing_location_is_disclosed():
    entries=[branch(lat=None,lon=None,location_source='unlocated')]
    assert not match_saved_selection([photo(lat=None,lon=None)],['a'],entries).candidates
    result=match_saved_selection([photo(lat=None,lon=None,venue_hints=('Café Élan',))],['a'],entries)
    assert len(result.candidates)==1 and result.candidates[0].distance_m is None
    assert 'Distance unavailable' in ' '.join(result.candidates[0].evidence)


def test_drifting_photo_does_not_hide_near_branch_and_range_is_disclosed():
    a=photo();b=photo(id='b',lat=40.02,taken=a.taken+timedelta(minutes=5))
    result=match_saved_selection([a,b],['a','b'],[branch(lat=40.0001)])
    assert result.candidates[0].distance_m<100
    assert result.candidates[0].distance_max_m>2000
    assert 'outside' in ' '.join(result.candidates[0].evidence)
    with pytest.raises(ValueError,match='scattered'):
        match_saved_selection([a,replace(b,lat=42)],['a','b'],[branch()])
    with pytest.raises(ValueError,match='three hours'):
        match_saved_selection([a,replace(b,taken=a.taken+timedelta(days=1))],['a','b'],[branch()])


@pytest.mark.parametrize('change', [dict(lat=91),dict(lon=float('nan')),dict(lon=None),
    dict(location_source='unlocated'),dict(beli_id=''),dict(name=' '),dict(address=' '),dict(osm_id='node/1')])
def test_invalid_catalog_entries_are_rejected(change):
    with pytest.raises(ValueError): branch(**change)


def test_additive_catalog_survives_restart_and_atomic_batches_preserve_legacy_and_approvals(tmp_path):
    path=tmp_path/'ledger.sqlite';ledger=Ledger(path)
    ledger.mark_added('old','Legacy','been','private rating')
    work=Worklist(ledger);catalog=SavedPlaces(ledger)
    group=match_saved_selection([photo()],['a'],[branch()]);work.save_match(group)
    catalog.upsert([branch()]);catalog.upsert([branch()])
    with pytest.raises(ValueError):catalog.upsert([branch(name='Valid first'),{'name':'invalid'}])
    with pytest.raises(ValueError):catalog.upsert([branch(),branch()])
    assert len(catalog.entries())==1 and ledger.is_handled('old')
    ledger.conn.close()
    reopened=Ledger(path)
    assert len(SavedPlaces(reopened).entries())==1
    assert Worklist(reopened).matches()[0].raw.photo_refs==['a']
    with sqlite3.connect(str(path)+'.bak') as backup:
        assert backup.execute('SELECT count(*) FROM assistant_saved_places').fetchone()[0]==1
    with sqlite3.connect(str(path)+'.pre-assistant.bak') as rollback:
        assert rollback.execute('SELECT name FROM handled').fetchone()[0]=='Legacy'
    assert path.stat().st_mode & 0o077 == 0


def test_auth_csrf_private_catalog_status_and_no_network_on_saved_match():
    p=Provider();app=discovery_app(photos=[photo()],provider=p)
    raw=TestClient(app,base_url="http://127.0.0.1:8000")
    assert raw.get('/api/saved-places').status_code==401
    assert raw.post('/api/saved-places',json={'entries':[branch().model_dump()]}).status_code==401
    c=connect(app)
    c.headers['Origin']='https://evil.test'
    assert c.post('/api/saved-places',json={'entries':[branch().model_dump()]}).status_code==403
    c.headers['Origin']='http://127.0.0.1:8000'
    assert c.post('/api/saved-places',json={'entries':[branch().model_dump()]}).json()['count']==1
    assert c.get('/api/discovery').json()['saved_places']['live_sync'] is False
    assert c.post('/api/discovery-match',json={'photos':['a'],'radius_m':1000}).status_code==200
    visit=c.get('/api/queue').json()['visits'][0]
    assert visit['candidates'][0]['candidate_source']=='beli_saved'
    assert not p.calls and not c.get('/api/session').json()['visits']
    assert c.post('/api/discovery-match',json={'photos':['a'],'radius_m':500}).status_code==200
    assert c.get('/api/queue').json()['visits'][0]['status']=='no_match'
    assert not p.calls
    assert c.post('/api/discovery-match',json={'photos':['a'],'radius_m':1000,'include_external':True}).status_code==200
    assert p.calls
    assert {x['candidate_source'] for x in c.get('/api/queue').json()['visits'][0]['candidates']}=={'provider','beli_saved'}
    before=len(p.calls)
    assert c.post('/api/discovery-match',json={'photos':['a'],'radius_m':999999}).status_code==422
    assert len(p.calls)==before


def test_catalog_update_cannot_rewrite_approved_progress_or_claim_beli_verification():
    c=connect(discovery_app(photos=[photo()]))
    c.post('/api/saved-places',json={'entries':[branch(list_status='been').model_dump()]})
    c.post('/api/discovery-match',json={'photos':['a']})
    visit=c.get('/api/queue').json()['visits'][0]
    c.post('/api/approve',json={'mappings':[{'visit_id':visit['visit_id'],
        'provider_id':visit['candidates'][0]['place_id'],'photos':['a']}]})
    old=c.get('/api/session').json()['visits']
    assert old[0]['ranking']=='pending' and not old[0]['beli_identity']
    assert old[0]['saved_list_status']=='been' and old[0]['candidate_source']=='beli_saved'
    c.post('/api/saved-places',json={'entries':[branch(list_status='unknown').model_dump()]})
    assert c.get('/api/session').json()['visits']==old
    assert c.post('/api/discovery-match',json={'photos':['a']}).status_code==409
    c.post('/api/control',json={'action':'start'})
    assert c.post('/api/saved-places',json={'entries':[branch().model_dump()]}).status_code==409


def test_external_failure_keeps_saved_candidates_and_unloaded_catalog_keeps_existing_flow():
    from beli_tool.places_client import PlacesError
    class Broken(Provider):
        def nearby_food(self,*args,**kwargs): raise PlacesError('private provider error')
    c=connect(discovery_app(photos=[photo()],provider=Broken()))
    c.post('/api/saved-places',json={'entries':[branch().model_dump()]})
    assert c.post('/api/discovery-match',json={'photos':['a'],'include_external':True}).status_code==200
    item=c.get('/api/queue').json()['visits'][0]
    assert item['candidates'] and 'unavailable' in item['match_note']
    assert 'private provider error' not in str(item)
    fresh=connect(discovery_app(photos=[photo()]))
    fresh.post('/api/discovery-match',json={'photos':['a']})
    assert 'not loaded' in fresh.get('/api/queue').json()['visits'][0]['match_note']
