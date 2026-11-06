"""Photo-first discovery: local labels suggest food; humans define each visit."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import unicodedata
from collections import Counter
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
    venue_hints: tuple[str, ...] = ()
    city_hint: str | None = None

    def public(self):
        return {'id': self.id, 'taken': self.taken.isoformat(), 'likely_food': self.food,
                'has_location': self.lat is not None and self.lon is not None,
                'preview_available': self.preview_available,
                'original_available': self.original_available,
                'screenshot': self.screenshot, 'venue_hints':list(self.venue_hints),
                'city_hint':self.city_hint}


def food_hint(labels, screenshot=False):
    return not screenshot and bool({str(v).casefold().strip() for v in labels or []} & _FOOD)


def _photo_group(assets: list[PhotoAsset], ids: list[str], name=None):
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
    raw = RawPlace(source='photos', name=name, lat=lat, lon=lon,
                   visit_date=selected[0].taken.date(), photo_count=len(selected),
                   photo_ref=selected[0].id, photo_refs=[a.id for a in selected])
    hints = Counter(); originals = {}
    cities = Counter(); city_originals = {}
    for asset in selected:
        seen_hints = set()
        for hint in asset.venue_hints:
            key = unicodedata.normalize('NFC', hint).casefold().strip()
            if key and key not in seen_hints:
                seen_hints.add(key)
                hints[key] += 1
                originals.setdefault(key, hint)
        if asset.city_hint:
            key = unicodedata.normalize('NFC', asset.city_hint).casefold().strip()
            cities[key] += 1; city_originals.setdefault(key, asset.city_hint)
    raw.venue_hints = [originals[key] for key, _ in hints.most_common(5)]
    raw.city_hint = city_originals[cities.most_common(1)[0][0]] if cities else None
    return raw, located


def match_selection(assets: list[PhotoAsset], ids: list[str], client, query=''):
    query = query.strip()
    raw, located = _photo_group(assets, ids, query or None)
    lat, lon = raw.lat, raw.lon
    def comparable(name):
        return ''.join(c for c in unicodedata.normalize('NFKD', name).casefold()
                       if not unicodedata.combining(c)).strip()
    def lookup(name, from_hint=False):
        # Recover the full original spelling for an exact accent-insensitive hint,
        # without guessing a different brand from a partial substring.
        if not from_hint:
            name = next((h for h in raw.venue_hints if comparable(h) == comparable(name)), name)
        name = unicodedata.normalize('NFC', name)
        contextual = name
        # A comma-qualified user query supplies its own address/city context.
        if raw.city_hint and (from_hint or ',' not in name) and comparable(raw.city_hint) not in comparable(name):
            contextual += ', ' + raw.city_hint
        nearby_name = getattr(client, 'text_search_context', None)
        if located and callable(nearby_name):
            return nearby_name(contextual, lat, lon)
        return client.text_search(contextual)
    if query:
        results = lookup(query)
    else:
        results = []
        for hint in raw.venue_hints[:3]:
            results.extend(lookup(hint, from_hint=True))
        food_types = {'restaurant','food','cafe','bar','bakery','meal_takeaway'}
        if not any(food_types & set(r.get('types', [])) for r in results):
            if not located:
                if not raw.venue_hints:
                    raise ValueError('These photos have no GPS or local venue name. Enter the restaurant name you recognize, or leave them pending.')
            else:
                if any(haversine_m(a.lat,a.lon,lat,lon)>150 for a in located):
                    raise ValueError('These photos have scattered locations. Select one visit, or search its restaurant by name.')
                results = client.nearby_food(lat,lon,radius_m=150)
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
    if raw.venue_hints:note+=' Existing Photos venue names were used as search hints, not verified identities.'
    if not located:note+=' No selected photo has GPS; these are name-search suggestions only.'
    if any(r.get('_requires_review') for r in results):note+=' OSM fallback results are incomplete.'
    return MatchedPlace(bucket='been',status='ambiguous' if candidates else 'no_match',
                        raw=raw,candidates=candidates,match_note=note)


def user_restaurant(assets: list[PhotoAsset], ids: list[str], name: str, address: str):
    """User testimony, not an OSM or Beli identity. No external request is made."""
    name, address = name.strip(), address.strip()
    if not name or not address:
        raise ValueError('Provide the full restaurant name and branch address/city')
    raw, _ = _photo_group(assets, ids, name)
    identity = hashlib.sha256(json.dumps([name, address], ensure_ascii=False).encode()).hexdigest()
    candidate = PlaceCandidate(place_id='user:' + identity, name=name, address=address,
                               category='restaurant')
    return MatchedPlace(bucket='been', status='ambiguous', raw=raw, candidates=[candidate],
        match_note='Name and address supplied by you; not verified by OSM or Beli. Check the exact branch in Beli before ranking or attaching photos.')
