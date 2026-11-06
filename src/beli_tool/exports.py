"""Export only approved local originals. Never touch Photos assets or sync settings."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps
from beli_tool.ledger import Ledger
from beli_tool.photos_source import OsxPhotosSource
from beli_tool.runtime import InstanceLock
from beli_tool.worklist import Worklist


def make_copy(original: Path, destination: Path):
    """Re-encode pixels without EXIF/GPS, IPTC, XMP or original filenames."""
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as folder:
        decoded = original
        if original.suffix.lower() in ('.heic', '.heif'):
            decoded = Path(folder) / 'decoded.jpg'
            subprocess.run(['/usr/bin/sips', '-s', 'format', 'jpeg', str(original), '--out', str(decoded)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with Image.open(decoded) as img:
            oriented = ImageOps.exif_transpose(img).convert('RGB')
            # Fresh image keeps pixels only; don't accidentally pass img.info.
            clean = Image.new('RGB', oriented.size)
            clean.paste(oriented)
            if max(clean.size) < 1024:
                raise ValueError('Original is too small for the trial; no thumbnail substitute was exported')
            temp = Path(folder) / 'clean.jpg'
            clean.save(temp, format='JPEG', quality=92, optimize=True)
        os.chmod(temp, 0o600)
        os.replace(temp, destination)
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def export_approved(cfg):
    os.umask(0o077)
    with InstanceLock(cfg.db_path.with_suffix('.worker.lock')):
        ledger = Ledger(cfg.db_path)
        work = Worklist(ledger)
        if work.snapshot()['status'] == 'running':
            raise RuntimeError('Stop the running review session before exporting')
        source = OsxPhotosSource(since=cfg.since, until=cfg.until, library_path=cfg.photos_library)
        source.points()  # index only the configured window; no matching/network
        export_home = cfg.db_path.parent / 'exports'
        export_home.mkdir(exist_ok=True, mode=0o700)
        root = Path(tempfile.mkdtemp(prefix='approved-', dir=export_home))
        manifest = []
        for visit in work.snapshot()['visits']:
            if visit['outcome'] != 'pending':
                continue
            for ref in visit['photos']:
                if visit['attachments'][ref] != 'pending':
                    continue
                original = source.approved_original_path(ref)
                if not original:
                    raise RuntimeError('An approved original is not locally available. Open Photos and download it there, then retry.')
                name = hashlib.sha256(ref.encode()).hexdigest() + '.jpg'
                digest = make_copy(Path(original), root / name)
                manifest.append({'visit_id':visit['visit_id'], 'photo_ref':ref,
                                 'file':name, 'sha256':digest,
                                 'iphone_availability':'not_verified'})
        temp = root / 'manifest.tmp'
        temp.write_text(json.dumps(manifest, indent=2)); temp.chmod(0o600)
        os.replace(temp, root / 'manifest.json')
        print(f'Exported {len(manifest)} approved copies to {root}. Originals were not modified.')
        print('These are Mac files, not iPhone picker selections. Transfer and verify one copy on the iPhone before attaching.')
