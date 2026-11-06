from __future__ import annotations

import logging
import secrets
import socket
import sys
from datetime import date

import uvicorn
from fastapi import FastAPI

from beli_tool import __version__
from beli_tool.config import LOG_PATH, Config, load_config
from beli_tool.ledger import Ledger
from beli_tool.logsetup import setup_logging
from beli_tool.maps_collector import collect_maps
from beli_tool.obsidian_log import ObsidianLog
from beli_tool.osm_client import OsmClient
from beli_tool.photos_collector import collect_photos
from beli_tool.photos_source import OsxPhotosSource
from beli_tool.pipeline import Queue, build_queue
from beli_tool.places_cache import PlacesCache
from beli_tool.places_client import PlacesClient, PlacesError
from beli_tool.webapp import create_app


log = logging.getLogger(__name__)


def describe(cfg: Config) -> str:
    """One-line config summary for the log. Deliberately never includes
    api_key: the log is a plain file and the key is the one secret here."""
    return (
        f"provider={cfg.provider} since={cfg.since} max_visits={cfg.max_visits} "
        f"saved_dir={cfg.saved_dir} db={cfg.db_path} "
        f"obsidian_log={'on' if cfg.obsidian_log else 'off'}"
    )


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def scan(cfg: Config, photo_source, client, ledger: Ledger) -> Queue:
    """Collect from both sources and match them. Repeatable: /api/rescan calls
    this again on the same ledger and cache, so a rescan is cheap and picks up
    newly-added photos or CSVs without a restart."""
    print("Photos-only: Maps import skipped." if cfg.photos_only else "Reading Google Maps saved lists…", flush=True)
    maps_places = [] if cfg.photos_only else collect_maps(cfg.saved_dir)
    print(f"  {len(maps_places)} saved place(s) found.", flush=True)

    window = f" taken since {cfg.since}" if cfg.since else " (whole library — set `since` in config.toml to bound this)"
    print(f"Reading Apple Photos for GPS-tagged photos{window}…", flush=True)
    photo_raws = collect_photos(photo_source)
    print(f"\r  {len(photo_raws)} photo visit(s) found.", flush=True)

    if cfg.max_visits and len(photo_raws) > cfg.max_visits:
        photo_raws.sort(key=lambda r: r.visit_date or date.min, reverse=True)
        skipped = len(photo_raws) - cfg.max_visits
        photo_raws = photo_raws[: cfg.max_visits]
        print(
            f"  Capping at the {cfg.max_visits} most recent visits "
            f"({skipped} older skipped — raise max_visits in config.toml to include them).",
            flush=True,
        )

    total = len(maps_places) + len(photo_raws)
    provider_name = "OpenStreetMap" if cfg.provider == "osm" else "Google Places"
    print(f"Matching {total} place(s) with {provider_name}…", flush=True)
    log.info(
        "scan: %d saved place(s), %d photo visit(s)%s",
        len(maps_places),
        len(photo_raws),
        f" since {cfg.since}" if cfg.since else " (whole library)",
    )
    queue = build_queue(
        maps_places,
        photo_raws,
        client,
        ledger,
        on_progress=lambda done, n: print(f"\r  {done}/{n}", end="", flush=True),
    )
    print(flush=True)
    hits = getattr(client, "hits", 0)
    if hits:
        print(f"  {hits} lookup(s) served from cache — no API charge.", flush=True)
    print(
        f"Ready: {len(queue.want_to_try)} to try, {len(queue.been)} been, "
        f"{len(queue.review)} unmatched.",
        flush=True,
    )
    log.info(
        "ready: %d to try, %d been, %d unmatched (%d cached, %d billed lookups)",
        len(queue.want_to_try),
        len(queue.been),
        len(queue.review),
        hits,
        getattr(client, "calls", 0),
    )
    return queue


def build_app_from_config(
    cfg: Config, photo_source=None, client=None, token=None, origin="http://127.0.0.1:8000"
) -> tuple[FastAPI, Ledger]:
    photo_source = photo_source or OsxPhotosSource(
        since=cfg.since, until=cfg.until, library_path=cfg.photos_library,
        on_progress=lambda n: print(f"\r  scanned {n} photos…", end="", flush=True),
    )
    ledger = Ledger(cfg.db_path)  # backup before cache/schema writes
    if client is None:
        cache = PlacesCache(cfg.db_path)
        if cfg.provider == "osm":
            client = OsmClient(cache=cache)
        else:
            client = PlacesClient(cfg.api_key, cache=cache)

    def rebuild() -> Queue:
        return scan(cfg, photo_source, client, ledger)

    discovery_enabled = cfg.photos_only and callable(getattr(photo_source, 'inventory', None))
    assets = photo_source.inventory() if discovery_enabled else None
    if assets is not None:
        print(f"Photo-first discovery: {len(assets)} images in the selected dates; "
              f"{sum(a.food for a in assets)} have local food labels. No coordinates sent yet.", flush=True)
        queue = Queue()
    else:
        queue = rebuild()
    def discovery():
        return assets
    def match_photos(ids, query):
        from beli_tool.discovery import match_selection
        return match_selection(assets, ids, client, query)
    photo_resolver = getattr(photo_source, "approved_preview_path", None) or getattr(photo_source, "thumbnail_path", None)
    obsidian_log = ObsidianLog(cfg.obsidian_log) if cfg.obsidian_log else None
    if obsidian_log:
        print(f"  Mirroring adds to {cfg.obsidian_log}", flush=True)
    app = create_app(
        queue,
        ledger,
        photo_resolver=photo_resolver,
        token=token,
        rebuild=None if discovery_enabled else rebuild,
        discovery=discovery if discovery_enabled else None,
        match_photos=match_photos if discovery_enabled else None,
        window=(cfg.since, cfg.until) if discovery_enabled else None,
        max_groups=cfg.max_visits,
        obsidian_log=obsidian_log,
        origin=origin,
    )
    return app, ledger


def main(argv: list[str] | None = None) -> None:
    import argparse
    import ipaddress
    import os
    from pathlib import Path
    from beli_tool.runtime import InstanceLock

    parser = argparse.ArgumentParser(description="Photos-only Beli review assistant")
    parser.add_argument('command', choices=['run', 'doctor', 'export-approved'])
    parser.add_argument('--config', type=Path)
    parser.add_argument('--pairing-dialog', action='store_true', help='Show pairing code only in a native Mac dialog')
    parser.add_argument('--phone-host', help="Mac LAN IP; requires trusted TLS certificate and key")
    parser.add_argument('--cert', type=Path)
    parser.add_argument('--key', type=Path)
    args = parser.parse_args(argv)
    os.umask(0o077)
    if args.command == 'doctor':
        from beli_tool.device import doctor
        doctor()
        return
    cfg = load_config(args.config)
    if args.command == 'export-approved':
        from beli_tool.exports import export_approved
        export_approved(cfg)
        return
    host = '127.0.0.1'
    if args.phone_host:
        address = ipaddress.ip_address(args.phone_host)
        if address.version != 4 or not address.is_private or address.is_loopback or address.is_unspecified:
            parser.error('--phone-host must be the Mac’s private LAN IPv4 address')
        if not args.cert or not args.key:
            parser.error('Phone access requires a trusted TLS certificate and private key; HTTP is refused')
        if args.key.stat().st_mode & 0o077:
            parser.error('Keep the TLS private key owner-only: chmod 600 on that key file')
        # Validate the cert/key before accessing Photos or sending coordinates.
        import ssl
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(args.cert), str(args.key))
        host = args.phone_host
    elif args.cert or args.key:
        parser.error('--cert/--key are only used together with --phone-host')
    origin = f"{'https' if args.phone_host else 'http'}://{host}:8000"
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with InstanceLock(cfg.db_path.with_suffix('.worker.lock')):
        setup_logging(cfg.db_path.parent / 'beli-tool.log')
        print('Matching sends photo coordinates to the selected outside provider. This is not offline.')
        try:
            app, ledger = build_app_from_config(cfg, origin=origin)
        except PlacesError:
            print('Matching service unavailable. No private provider details were logged.', file=sys.stderr)
            raise SystemExit(1)
        except Exception:
            print('Photos or local state could not be opened. Open Photos, check the selected library and Full Disk Access for the app running this command. No private error details were logged.', file=sys.stderr)
            raise SystemExit(1)
        print(f"Open {origin} on {'your iPhone' if args.phone_host else 'this Mac'}")
        if args.pairing_dialog:
            import threading
            from beli_tool.desktop import pair_when_ready
            threading.Thread(target=pair_when_ready, args=(origin, host, app.state.pairing_code), daemon=True).start()
            print('The pairing code will appear in a private Mac dialog, not this output.')
        else:
            print(f"One-time pairing code (expires in 10 minutes): {app.state.pairing_code}")
        print('No verified Beli device automation is active. Use manual review controls.')
        print('Stop with Control-C. Progress stays in the local worklist.')
        try:
            uvicorn.run(app, host=host, port=8000, access_log=False, proxy_headers=False,
                        ssl_certfile=str(args.cert) if args.cert else None,
                        ssl_keyfile=str(args.key) if args.key else None,
                        ssl_version=__import__('ssl').PROTOCOL_TLS_SERVER,
                        log_level='warning')
        finally:
            ledger.conn.close()
