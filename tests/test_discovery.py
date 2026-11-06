from datetime import date, datetime, timedelta
import pytest
from beli_tool.discovery import PhotoAsset, food_hint, match_selection
from beli_tool.ledger import Ledger
from beli_tool.pipeline import Queue
from beli_tool.webapp import create_app
from beli_tool.worklist import Worklist, visit_id
from test_webapp import connect


def assets(count=9):
    return [PhotoAsset(str(i),datetime(2026,10,24,12)+timedelta(minutes=i),
        40.0 if i else None,-73.0 if i else None,i%2==0,True,False) for i in range(count)]


class Provider:
    def __init__(self):self.calls=[]
    def nearby_food(self,lat,lon,radius_m):
        self.calls.append(('nearby',radius_m));return self.result()
    def text_search(self,query):
        self.calls.append(('name',query));return self.result()
    def result(self):
        return [{'place_id':'osm:node/1','name':'O’Malley’s 東京','types':['restaurant'],
                 'vicinity':'1 Test Street','geometry':{'location':{'lat':40.0,'lng':-73.0}}}]


def discovery_app(ledger=None, photos=None, provider=None, **kwargs):
    photos=photos if photos is not None else assets()
    provider=provider or Provider()
    return create_app(Queue(),ledger or Ledger(),discovery=lambda:photos,
        match_photos=lambda ids,query:match_selection(photos,ids,provider,query),
        window=(date(2026,10,23),date(2026,10,29)),**kwargs)


def test_food_hints_do_not_promote_interiors_screenshots_or_unknown_images():
    assert food_hint(['Food','Dish'])
    assert food_hint(['COFFEE'])
    assert not food_hint(['restaurant','tableware'])
    assert not food_hint(['Food'],screenshot=True)
    assert not food_hint([])


def test_selection_preserves_all_photos_and_never_confirms_restaurant():
    provider=Provider();selection=assets(12)
    result=match_selection(selection,[p.id for p in selection],provider)
    assert result.raw.photo_count==12 and len(result.raw.photo_refs)==12
    assert result.status=='ambiguous' and result.match is None
    assert provider.calls==[('nearby',150)]
    assert result.raw.photo_refs[0]=='0'  # no-GPS food is retained in this user-defined visit


def test_unknown_duplicate_and_multi_visit_selections_never_make_network_calls():
    p=Provider();photos=assets()
    for ids in (['outside'],['1','1']):
        with pytest.raises(ValueError):match_selection(photos,ids,p)
    far=PhotoAsset('later',datetime(2026,10,25,12),40,-73,True,True,False)
    with pytest.raises(ValueError,match='three hours'):match_selection(photos+[far],['1','later'],p)
    assert not p.calls


def test_without_gps_is_visible_and_can_use_explicit_name_search():
    p=Provider();photos=assets(1)
    with pytest.raises(ValueError,match='no GPS'):match_selection(photos,['0'],p)
    result=match_selection(photos,['0'],p,'Restaurant, city')
    assert result.status=='ambiguous' and result.raw.lat is None
    assert p.calls==[('name','Restaurant, city')]


def test_discovery_includes_entire_window_without_automatic_provider_calls():
    p=Provider();c=connect(discovery_app(photos=assets(90),provider=p))
    data=c.get('/api/discovery').json()
    assert len(data['photos'])==90 and data['without_gps']==1
    assert data['likely_food']==45
    assert 'lat' not in data['photos'][1] and 'lon' not in data['photos'][1]
    assert not p.calls
    assert c.get('/api/queue').json()['visits']==[]
    assert c.post('/api/discovery-match',json={'photos':['outside']}).status_code==409
    assert not p.calls


def test_draft_group_name_correction_persists_without_duplicate_or_lost_photos(tmp_path):
    led=Ledger(tmp_path/'l.sqlite');p=Provider();app=discovery_app(ledger=led,provider=p);c=connect(app)
    ids=[a.id for a in assets()]
    assert c.post('/api/discovery-match',json={'photos':ids}).status_code==200
    old=c.get('/api/queue').json()['visits'][0]
    assert c.post('/api/discovery-match',json={'photos':ids,'query':'Correct restaurant, city'}).status_code==200
    rows=c.get('/api/queue').json()['visits'];assert len(rows)==1
    assert rows[0]['visit_id']==old['visit_id'] and len(rows[0]['photos'])==9
    # A fresh application restores the exact unapproved group from SQLite.
    fresh=connect(discovery_app(ledger=led))
    assert fresh.get('/api/queue').json()['visits'][0]['photos']==ids
    mapping={'visit_id':rows[0]['visit_id'],'provider_id':'osm:node/1','photos':ids}
    assert fresh.post('/api/approve',json={'mappings':[mapping]}).status_code==200
    assert fresh.post('/api/remove-match',json={'visit_id':rows[0]['visit_id']}).status_code==409
    assert len(fresh.get('/api/session').json()['visits'][0]['photos'])==9


def test_unapproved_group_can_be_returned_but_overlaps_cannot_duplicate_it():
    c=connect(discovery_app())
    assert c.post('/api/discovery-match',json={'photos':['1','2']}).status_code==200
    assert c.post('/api/discovery-match',json={'photos':['2','3']}).status_code==409
    ident=c.get('/api/queue').json()['visits'][0]['visit_id']
    assert c.post('/api/remove-match',json={'visit_id':ident}).status_code==200
    assert c.post('/api/discovery-match',json={'photos':['2','3']}).status_code==200


def test_user_restaurant_keeps_provider_and_beli_identity_separate_and_never_calls_provider():
    from beli_tool.discovery import user_restaurant
    p=Provider();photos=assets(1)
    item=user_restaurant(photos,['0'],' Mắm 東京 ', ' 1 Test Street, Test City ')
    assert item.status=='ambiguous' and item.match is None
    assert item.candidates[0].place_id.startswith('user:')
    assert item.candidates[0].name=='Mắm 東京'
    assert 'not verified by OSM or Beli' in item.match_note
    assert not p.calls
    with pytest.raises(ValueError):user_restaurant(photos,['outside'],'Name','Address')
    with pytest.raises(ValueError):user_restaurant(photos,['0'],'  ','Address')


def test_user_supplied_branch_replaces_draft_without_approving_photos_or_verifying_beli():
    p=Provider();c=connect(discovery_app(provider=p))
    assert c.post('/api/discovery-match',json={'photos':['1']}).status_code==200
    original=c.get('/api/queue').json()['visits'][0]
    c.headers['Origin']='https://evil.test'
    assert c.post('/api/user-restaurant',json={'photos':['1'],'name':'Name','address':'Address'}).status_code==403
    c.headers['Origin']='http://127.0.0.1:8000'
    count=len(p.calls)
    request={'photos':['1'],'name':'User restaurant','address':'1 Test Street, Test City'}
    assert c.post('/api/user-restaurant',json=request).status_code==200
    rows=c.get('/api/queue').json()['visits'];assert len(rows)==1
    assert rows[0]['visit_id']==original['visit_id']
    assert rows[0]['candidates'][0]['place_id'].startswith('user:')
    assert not c.get('/api/session').json()['visits']
    assert len(p.calls)==count
    m={'visit_id':rows[0]['visit_id'],'provider_id':rows[0]['candidates'][0]['place_id'],'photos':['1']}
    assert c.post('/api/approve',json={'mappings':[m]}).status_code==200
    saved=c.get('/api/session').json()['visits'][0]
    assert saved['beli_identity'] is None and saved['ranking']=='pending'
    assert saved['attachments']=={'1':'pending'}
    assert c.post('/api/user-restaurant',json={**request,'address':'Another branch'}).status_code==409
    assert c.get('/api/session').json()['visits'][0]['address']==request['address']


def test_group_removal_cannot_race_an_inflight_lookup():
    import threading
    entered=threading.Event();release=threading.Event()
    class SlowProvider(Provider):
        slow=False
        def nearby_food(self,*args,**kwargs):
            if self.slow:
                entered.set();assert release.wait(5)
            return super().nearby_food(*args,**kwargs)
    p=SlowProvider();c=connect(discovery_app(provider=p))
    assert c.post('/api/discovery-match',json={'photos':['1']}).status_code==200
    ident=c.get('/api/queue').json()['visits'][0]['visit_id']
    p.slow=True;results=[]
    t=threading.Thread(target=lambda:results.append(c.post('/api/discovery-match',json={'photos':['2']}).status_code))
    t.start()
    try:
        assert entered.wait(3)
        assert c.post('/api/remove-match',json={'visit_id':ident}).status_code==409
    finally:
        release.set();t.join(5)
    assert not t.is_alive() and results==[200]
    assert len(c.get('/api/queue').json()['visits'])==2


def test_cached_photos_venue_and_city_are_used_before_generic_nearby_search():
    class ContextProvider(Provider):
        def text_search_context(self,query,lat,lon):
            self.calls.append(('context',query,lat,lon));return self.result()
        def nearby_food(self,*args,**kwargs):
            raise AssertionError('Generic nearby search should not replace a successful venue hint')
    photo=PhotoAsset('hinted',datetime(2026,10,24,12),40,-73,True,True,False,
                     venue_hints=('Cafe\u0301 E\u0301lan',),city_hint='Test City')
    p=ContextProvider();result=match_selection([photo],['hinted'],p)
    assert p.calls==[('context','Café Élan, Test City',40,-73)]
    assert result.status=='ambiguous' and result.match is None
    assert result.raw.venue_hints==['Cafe\u0301 E\u0301lan']
    assert 'not verified identities' in result.match_note


def test_ascii_name_uses_cached_spelling_and_city_without_gps():
    photo=PhotoAsset('hinted',datetime(2026,10,24,12),None,None,True,True,False,
                     venue_hints=('Café Élan',),city_hint='Test City')
    p=Provider();result=match_selection([photo],['hinted'],p,'cafe elan')
    assert p.calls==[('name','Café Élan, Test City')]
    assert result.raw.lat is None and result.status=='ambiguous'


def test_canonical_equivalent_hints_count_once_and_remain_stable():
    photo=PhotoAsset('hinted',datetime(2026,10,24,12),40,-73,True,True,False,
        venue_hints=('Cafe\u0301 E\u0301lan','Café Élan','Another restaurant'),city_hint='Test City')
    result=match_selection([photo],['hinted'],Provider())
    assert result.raw.venue_hints==['Cafe\u0301 E\u0301lan','Another restaurant']


def test_explicit_city_correction_is_not_overridden_by_cached_photo_city():
    photo=PhotoAsset('hinted',datetime(2026,10,24,12),None,None,True,True,False,
                     venue_hints=('Café Élan',),city_hint='Old City')
    p=Provider();match_selection([photo],['hinted'],p,'Café Élan, Correct City')
    assert p.calls==[('name','Café Élan, Correct City')]
