"""Photo-first discovery: local labels suggest food; humans define each visit."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from beli_tool.clustering import haversine_m
from beli_tool.models import MatchedPlace, PlaceCandidate, RawPlace

# Restaurant/interior/tableware labels alone are intentionally not food evidence.
_FOOD = {'food','foods','dish','dishes','meal','meals','cuisine','dessert','desserts',
         'drink','drinks','beverage','beverages','pizza','sushi','cake','cakes','bread',
         'coffee','lunch','dinner','breakfast','sandwich','sandwiches','noodles','salad'}


@dataclass(frozen=True)
class PhotoAsset:
    id: str
    taken: datetime
    lat: float | None
    lon: float | None
    food: bool
    preview_available: bool
    original_available: bool
    screenshot: bool = False

    def public(self):
        return {'id': self.id, 'taken': self.taken.isoformat(), 'likely_food': self.food,
                'has_location': self.lat is not None and self.lon is not None,
                'preview_available': self.preview_available,
                'original_available': self.original_available,
                'screenshot': self.screenshot}


def food_hint(labels, screenshot=False):
    return not screenshot and bool({str(v).casefold().strip() for v in labels or []} & _FOOD)


def match_selection(assets: list[PhotoAsset], ids: list[str], client, query=''):
    query = query.strip()
    if not ids or len(ids) != len(set(ids)) or len(ids)>100:
        raise ValueError('Choose 1–100 different photos from one visit')
    by_id={a.id:a for a in assets}
    if not set(ids)<=by_id.keys():
        raise ValueError('A selected photo is outside this date window; refresh discovery')
    selected=sorted((by_id[i] for i in ids),key=lambda a:a.taken)
    if (selected[-1].taken-selected[0].taken).total_seconds()>3*3600:
        raise ValueError('These photos span more than three hours. Select photos from one visit at a time.')
    located=[a for a in selected if a.lat is not None and a.lon is not None]
    lat=sum(a.lat for a in located)/len(located) if located else None
    lon=sum(a.lon for a in located)/len(located) if located else None
    if not query:
        if not located:
            raise ValueError('These photos have no GPS. Enter the restaurant name you recognize, or leave them pending.')
        if any(haversine_m(a.lat,a.lon,lat,lon)>150 for a in located):
            raise ValueError('These photos have scattered locations. Select one visit, or search its restaurant by name.')
        results=client.nearby_food(lat,lon,radius_m=150)
    else:
        results=client.text_search(query.strip())
    raw=RawPlace(source='photos',name=query.strip() or None,lat=lat,lon=lon,
                 visit_date=selected[0].taken.date(),photo_count=len(selected),
                 photo_ref=selected[0].id,photo_refs=[a.id for a in selected])
    candidates=[];seen=set()
    for r in results:
        if not {'restaurant','food','cafe','bar','bakery','meal_takeaway'} & set(r.get('types',[])):
            continue
        ident=r['place_id']
        if ident in seen:continue
        seen.add(ident)
        point=r.get('geometry',{}).get('location',{})
        distance=None
        if lat is not None and all(isinstance(point.get(k),(int,float)) and isfinite(point[k]) for k in ('lat','lng')):
            distance=haversine_m(lat,lon,point['lat'],point['lng'])
        candidates.append(PlaceCandidate(place_id=ident,name=r['name'],
            address=r.get('formatted_address') or r.get('vicinity',''),
            category=(r.get('types') or ['restaurant'])[0],distance_m=distance))
    if not query:candidates.sort(key=lambda c:c.distance_m if c.distance_m is not None else float('inf'))
    note=('You selected these photos as one visit. GPS and local food labels do not prove the restaurant. '
          'Check the full branch address; use restaurant-name search if these suggestions are wrong.')
    if not located:note+=' No selected photo has GPS; these are name-search suggestions only.'
    if any(r.get('_requires_review') for r in results):note+=' OSM fallback results are incomplete.'
    return MatchedPlace(bucket='been',status='ambiguous' if candidates else 'no_match',
                        raw=raw,candidates=candidates,match_note=note)
