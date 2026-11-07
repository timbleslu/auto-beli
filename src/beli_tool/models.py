from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class RawPlace(BaseModel):
    source: Literal["maps", "photos"]
    name: str | None = None
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    visit_date: date | None = None
    photo_ref: str | None = None
    photo_refs: list[str] = Field(default_factory=list)
    photo_count: int = 0
    source_list: str | None = None
    venue_hints: list[str] = Field(default_factory=list)
    city_hint: str | None = None


class PlaceCandidate(BaseModel):
    place_id: str
    name: str
    address: str
    category: str
    distance_m: float | None = None
    distance_max_m: float | None = None
    candidate_source: Literal['provider', 'beli_saved'] = 'provider'
    saved_list_status: Literal['been', 'want_to_try', 'unknown'] | None = None
    beli_id: str | None = None
    evidence: list[str] = Field(default_factory=list)


class MatchedPlace(BaseModel):
    bucket: Literal["been", "want_to_try"]
    status: Literal["confident", "ambiguous", "no_match"]
    raw: RawPlace
    match: PlaceCandidate | None = None
    candidates: list[PlaceCandidate] = Field(default_factory=list)
    match_note: str | None = None
