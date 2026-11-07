"""Private Beli shortlist. Membership is evidence for review, never a verified visit.

Phone acquisition is deliberately separate: callers supply observed entries, not
account credentials or undocumented Beli APIs. No network requests occur here.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from beli_tool.clustering import haversine_m
from beli_tool.discovery import _photo_group
from beli_tool.models import MatchedPlace, PlaceCandidate


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text).casefold()
                   if not unicodedata.combining(c)).strip()


class SavedPlace(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=500)
    # Only an identity actually observed in Beli belongs here; OSM IDs stay separate.
    beli_id: str | None = Field(default=None, min_length=1, max_length=200)
    list_status: Literal['been', 'want_to_try', 'unknown'] = 'unknown'
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    location_source: Literal['unlocated', 'beli_ui', 'user_confirmed_address'] = 'unlocated'

    @model_validator(mode='after')
    def coordinates_have_provenance(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError('Supply both coordinates or neither')
        if (self.lat is None) != (self.location_source == 'unlocated'):
            raise ValueError('Located entries need an observed or address-confirmed location source')
        return self

    @property
    def key(self):
        identity = ['beli', self.beli_id] if self.beli_id else ['branch', normalized(self.name), normalized(self.address)]
        # Local catalog identity is not claimed to be a Beli restaurant identifier.
        return 'beli_saved:' + hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


class SavedPlaces:
    def __init__(self, ledger):
        self.ledger = ledger
        with ledger._lock, ledger.conn:
            ledger.conn.execute('''CREATE TABLE IF NOT EXISTS assistant_saved_places (
                entry_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')))''')

    def entries(self):
        with self.ledger._lock:
            return [SavedPlace.model_validate_json(row[0]) for row in self.ledger.conn.execute(
                'SELECT payload FROM assistant_saved_places ORDER BY entry_id')]

    def upsert(self, entries):
        # Validate the complete batch BEFORE writing. Partial UI captures add/update
        # entries, never delete previously observed places or approved progress.
        entries = [SavedPlace.model_validate(e) for e in entries]
        if len({e.key for e in entries}) != len(entries):
            raise ValueError('Duplicate branch entries in this batch')
        with self.ledger._lock, self.ledger.conn:
            self.ledger.conn.executemany('''INSERT INTO assistant_saved_places(entry_id,payload)
                VALUES (?,?) ON CONFLICT(entry_id) DO UPDATE SET payload=excluded.payload,
                updated_at=datetime('now')''', [(e.key, e.model_dump_json()) for e in entries])

    def summary(self):
        entries = self.entries()
        return {'count':len(entries), 'located':sum(e.lat is not None for e in entries),
                'been':sum(e.list_status == 'been' for e in entries),
                'want_to_try':sum(e.list_status == 'want_to_try' for e in entries),
                'live_sync':False}


def match_saved_selection(assets, ids, entries, query='', radius_m=1000):
    """Rank within a user-selected net, retain branches and ambiguity.

    Use the nearest individual photo rather than the centroid: one drifting GPS
    point must not hide an otherwise plausible branch. Display the full range
    and flag disagreement. Timestamps group visits, not saved-list membership.
    """
    if radius_m not in (250, 500, 1000, 2000):
        raise ValueError('Choose a search distance of 250, 500, 1000 or 2000 metres')
    query = query.strip()
    raw, located = _photo_group(assets, ids, query or None)
    if located and any(haversine_m(a.lat, a.lon, raw.lat, raw.lon) > 2 * radius_m for a in located):
        raise ValueError('These photos have widely scattered locations. Select one visit before matching.')
    hints = {normalized(h) for h in raw.venue_hints}
    query_terms = set(re.findall(r'\w+', normalized(query)))
    ranked = []
    for entry in entries:
        distances = [haversine_m(a.lat,a.lon,entry.lat,entry.lon) for a in located] if entry.lat is not None else []
        near = min(distances) if distances else None
        far = max(distances) if distances else None
        name_hint = normalized(entry.name) in hints
        # An explicit query can locate a corrected branch outside the GPS radius;
        # it is always labelled and never silently overridden by cached hints.
        branch_terms = set(re.findall(r'\w+', normalized(entry.name + ', ' + entry.address)))
        query_match = bool(query_terms) and query_terms <= branch_terms
        if query:
            if not query_match:
                continue
        elif near is not None:
            if near > radius_m:
                continue
        elif not name_hint:
            continue  # Do not offer the entire saved list when GPS/hints are absent.
        evidence = ['Saved in your Beli shortlist; current Beli state must be checked']
        if name_hint:
            evidence.append('Name agrees with a Photos venue hint')
        if near is None:
            evidence.append('Distance unavailable; branch location needs checking')
        elif far > radius_m:
            evidence.append('Some or all photo locations are outside the chosen range')
        if entry.list_status == 'been':
            evidence.append('Already on Been list: check existing ranking before any changes')
        candidate = PlaceCandidate(place_id=entry.key, name=entry.name, address=entry.address,
            category='restaurant', distance_m=near, distance_max_m=far,
            candidate_source='beli_saved', saved_list_status=entry.list_status,
            beli_id=entry.beli_id, evidence=evidence)
        ranked.append((not name_hint, near if near is not None else float('inf'), entry.key, candidate))
    ranked.sort(key=lambda row:row[:3])
    return MatchedPlace(bucket='been', status='ambiguous' if ranked else 'no_match', raw=raw,
        candidates=[row[3] for row in ranked], match_note=(
            f'Compared with your local Beli shortlist within {radius_m} m. '
            'A saved place, nearby GPS and a name hint do not prove a visit or identify a photo. '
            'Check the exact branch and approve the photos. No external lookup was made. '
            'Explicit name/address searches can include saved branches outside this range. '
            'If missing, widen the range or explicitly include OSM suggestions.'))
