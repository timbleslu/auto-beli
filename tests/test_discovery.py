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
