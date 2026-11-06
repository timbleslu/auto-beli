from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from beli_tool.clustering import PhotoPoint


class PhotoSource(Protocol):
    def points(self) -> list[PhotoPoint]: ...


class OsxPhotosSource:
    """Reads local Photos metadata; offers bounded image discovery and a legacy GPS source.

    The Photos database is opened once and reused, and the matched photos are
    indexed by UUID so ``thumbnail_path`` can resolve a card's image to a
    browser-displayable derivative without re-reading the library per request.

    ``since`` bounds the scan to photos taken on/after that date, pushed down
    into osxphotos rather than filtered here. Without it, every run walks the
    entire library and every old visit costs another Places lookup.
    """

    def __init__(self, since: date | None = None, on_progress=None, until: date | None = None, library_path: str | Path | None = None) -> None:
        self._db = None
        self._library_path = library_path
        self._by_uuid: dict = {}
        self._since = since
        self._until = until
        self._on_progress = on_progress

    def _get_db(self):
        if self._db is None:
            import osxphotos

            if self._library_path is not None:
                self._db = osxphotos.PhotosDB(dbfile=str(self._library_path))
            else:
                self._db = osxphotos.PhotosDB()
        return self._db

    def probe(self) -> str | None:
        """Return None if the Photos library is readable, else an error string.

        osxphotos reads the library's sqlite directly, which macOS gates behind
        Full Disk Access. FDA has *no* automatic prompt, so opening the DB
        just fails. We try it once here; the opened DB is cached for points().
        """
        try:
            self._get_db()
            return None
        except Exception as e:  # noqa: BLE001 - any open failure is user-actionable
            return str(e)

    def points(self) -> list[PhotoPoint]:
        db = self._get_db()
        kwargs = {}
        if self._since is not None:
            kwargs["from_date"] = datetime.combine(self._since, datetime.min.time())
        if self._until is not None:
            kwargs["to_date"] = datetime.combine(self._until, datetime.max.time())
        out: list[PhotoPoint] = []
        self._by_uuid.clear()
        for i, p in enumerate(db.photos(**kwargs), 1):
            if self._on_progress and i % 500 == 0:
                self._on_progress(i)
            loc = p.location  # (lat, lon) or (None, None)
            if loc and loc[0] is not None and loc[1] is not None and p.date:
                self._by_uuid[p.uuid] = p
                out.append(PhotoPoint(id=p.uuid, lat=loc[0], lon=loc[1], taken=p.date))
        return out

    def thumbnail_path(self, uuid: str) -> str | None:
        """Resolve an indexed photo UUID to an available browser-displayable image.

        Prefers the largest available JPEG/PNG derivative for clearer review;
        falls back to an original path if one exists. Returns None if unknown.
        """
        p = self._by_uuid.get(uuid)
        if p is None:
            return None
        derivatives = [d for d in (p.path_derivatives or []) if d and Path(d).suffix.lower() in (".jpg", ".jpeg", ".png") and os.path.isfile(d)]
        if derivatives:
            return max(derivatives, key=os.path.getsize)
        if p.path and os.path.exists(p.path):
            return p.path
        return None

    def original_path(self, uuid: str) -> str | None:
        """Local full-size original only. Never substitutes a thumbnail or downloads."""
        p = self._by_uuid.get(uuid)
        if p is not None and p.path and os.path.isfile(p.path):
            return p.path
        return None

    def inventory(self):
        """All visible images in the bounded window, including those without GPS.

        Reads only existing Photos categorization. No image pixels go to any AI.
        Food labels are hints; screenshots and unlabelled images remain reviewable.
        """
        from datetime import timedelta
        from beli_tool.discovery import PhotoAsset, food_hint
        if self._since is None or self._until is None:
            raise ValueError('Photo discovery requires a bounded date range')
        db = self._get_db()
        photos = db.photos(images=True, movies=False,
            from_date=datetime.combine(self._since, datetime.min.time()),
            to_date=datetime.combine(self._until + timedelta(days=1), datetime.min.time()))
        assets=[]
        for p in photos:
            if not p.date or getattr(p,'hidden',False):
                continue
            self._by_uuid[p.uuid]=p
            loc=p.location or (None,None)
            try:labels=p.labels or []
            except (AttributeError,KeyError):labels=[]
            screenshot=bool(getattr(p,'screenshot',False))
            hints=(); city=None
            try:
                info=getattr(p,'search_info',None)
                place=getattr(p,'place',None)
                # Don't turn Photos' home-place metadata into an automatic business query.
                if not getattr(place,'ishome',False):
                    names=getattr(info,'venues',[]) or []
                    hints=tuple(dict.fromkeys(str(n).strip() for n in names
                        if isinstance(n,str) and n.strip() and len(n)<=200))[:10]
                city=(getattr(info,'city',None) or '').strip()[:120] or None
            except Exception:
                # Optional metadata can be absent/unreadable; keep the image visible
                # and fall back to GPS/manual search, without logging private text.
                hints=(); city=None
            assets.append(PhotoAsset(id=p.uuid,taken=p.date,lat=loc[0],lon=loc[1],
                food=food_hint(labels,screenshot),preview_available=self.thumbnail_path(p.uuid) is not None,
                original_available=self.original_path(p.uuid) is not None,screenshot=screenshot,
                venue_hints=hints,city_hint=city))
        return sorted(assets,key=lambda a:a.taken,reverse=True)

    def _asset(self, uuid):
        p=self._by_uuid.get(uuid)
        if p is None:
            # Callers must enforce their queue/discovery/approval allowlist first.
            # UUID lookup resolves a Photos asset, never a caller-supplied file path.
            matches=self._get_db().photos_by_uuid([uuid])
            p=matches[0] if matches else None
            if p is not None:self._by_uuid[uuid]=p
        return p

    def approved_preview_path(self, uuid):
        self._asset(uuid)
        return self.thumbnail_path(uuid)

    def approved_original_path(self, uuid):
        self._asset(uuid)
        return self.original_path(uuid)
