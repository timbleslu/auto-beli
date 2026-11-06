"""Additive, transactional worklist. Legacy handled rows remain untouched.

Manual confirmations are deliberately distinct from machine verification.
No web request can manufacture verified evidence.
"""
from __future__ import annotations

import hashlib
import json
from beli_tool.ledger import Ledger


def visit_id(item) -> str:
    raw = item.raw
    identity = [raw.source, raw.visit_date.isoformat() if raw.visit_date else None,
                sorted(raw.photo_refs or ([raw.photo_ref] if raw.photo_ref else [])),
                raw.name, raw.source_list]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


class Worklist:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        with ledger._lock, ledger.conn:
            ledger.conn.execute('''CREATE TABLE IF NOT EXISTS assistant_visits (
                visit_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                outcome TEXT NOT NULL DEFAULT 'pending')''')
            ledger.conn.execute('''CREATE TABLE IF NOT EXISTS assistant_session (
                id INTEGER PRIMARY KEY CHECK(id=1), status TEXT NOT NULL)''')
            ledger.conn.execute("INSERT OR IGNORE INTO assistant_session VALUES (1, 'idle')")
            # Restart always requires explicit Resume; never resume phone taps.
            ledger.conn.execute("UPDATE assistant_session SET status='paused' WHERE status='running'")

    def approve(self, mappings: list[dict]):
        ids = [m['visit_id'] for m in mappings]
        if len(ids) != len(set(ids)):
            raise ValueError('A visit occurs twice in this batch')
        with self.ledger._lock, self.ledger.conn:
            for m in mappings:
                old = self.ledger.conn.execute(
                    'SELECT payload FROM assistant_visits WHERE visit_id=?', (m['visit_id'],)).fetchone()
                if old:
                    prior = json.loads(old[0])
                    keys = ('provider_id', 'photos', 'name', 'address')
                    # Do not overwrite prior confirmations or retry uploads on reapproval.
                    if any(prior[k] != m[k] for k in keys):
                        raise ValueError('This visit is already approved; finish it before changing its mapping')
                    continue
                payload = {**m, 'ranking': 'pending',
                           'attachments': {ref: 'pending' for ref in m['photos']},
                           'beli_identity': None}
                self.ledger.conn.execute('INSERT INTO assistant_visits(visit_id,payload) VALUES (?,?)',
                                         (m['visit_id'], json.dumps(payload)))

    def snapshot(self):
        with self.ledger._lock:
            status = self.ledger.conn.execute('SELECT status FROM assistant_session WHERE id=1').fetchone()[0]
            rows = self.ledger.conn.execute('SELECT payload,outcome FROM assistant_visits ORDER BY rowid').fetchall()
        visits = [{**json.loads(row[0]), 'outcome': row[1]} for row in rows]
        current = next((v for v in visits if v['outcome'] == 'pending'), None)
        return {'status': status, 'visits': visits, 'current': current,
                'automation_verified': False, 'mode': 'manual'}

    def control(self, action):
        with self.ledger._lock, self.ledger.conn:
            old = self.ledger.conn.execute('SELECT status FROM assistant_session WHERE id=1').fetchone()[0]
            transitions = {('idle','start'): 'running', ('stopped','start'): 'running',
                           ('paused','resume'): 'running', ('running','pause'): 'paused'}
            if action == 'stop':
                new = 'stopped'
            else:
                new = transitions.get((old, action))
                if new is None:
                    raise ValueError('That session control is unavailable now')
            if new == 'running' and not self.ledger.conn.execute(
                "SELECT 1 FROM assistant_visits WHERE outcome='pending'").fetchone():
                raise ValueError('Approve at least one pending visit first')
            self.ledger.conn.execute('UPDATE assistant_session SET status=? WHERE id=1', (new,))

    def manual(self, ident, action, photo=None, name=None, address=None):
        """Explicit user testimony only. Never call these machine verified."""
        with self.ledger._lock, self.ledger.conn:
            status = self.ledger.conn.execute('SELECT status FROM assistant_session WHERE id=1').fetchone()[0]
            if status != 'running':
                raise ValueError('Start or resume the session first')
            row = self.ledger.conn.execute(
                "SELECT visit_id,payload FROM assistant_visits WHERE outcome='pending' ORDER BY rowid LIMIT 1").fetchone()
            if not row or row[0] != ident:
                raise ValueError('This is no longer the current visit')
            m = json.loads(row[1]); outcome = 'pending'
            if action == 'identity':
                if name != m['name'] or address != m['address']:
                    raise ValueError('Confirm the exact name and address shown in the approved mapping')
                m['beli_identity'] = {'name': name, 'address': address, 'source': 'user_confirmed'}
            elif action == 'skip':
                outcome = 'skipped'  # separate from completion, survives restart
            elif not m['beli_identity']:
                raise ValueError('Check the Beli branch name and address first')
            elif action == 'ranking':
                m['ranking'] = 'user_confirmed'
            elif action == 'photo':
                if m['ranking'] == 'pending' or photo not in m['attachments']:
                    raise ValueError('Confirm ranking and choose an approved photo')
                m['attachments'][photo] = 'user_confirmed'
            elif action in ('finish', 'finish_without_photos'):
                if m['ranking'] == 'pending':
                    raise ValueError('Ranking is still pending')
                if action == 'finish' and any(s == 'pending' for s in m['attachments'].values()):
                    raise ValueError('Requested photos are still pending')
                if action == 'finish_without_photos':
                    m['attachments'] = {r: 'waived_by_user' if s == 'pending' else s
                                        for r,s in m['attachments'].items()}
                outcome = 'user_finished'  # never called verified/complete
            else:
                raise ValueError('Unknown action')
            self.ledger.conn.execute('UPDATE assistant_visits SET payload=?,outcome=? WHERE visit_id=?',
                                     (json.dumps(m),outcome,ident))
