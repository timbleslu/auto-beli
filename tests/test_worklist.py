import sqlite3
import pytest
from beli_tool.ledger import Ledger
from beli_tool.worklist import Worklist, visit_id
from beli_tool.runtime import InstanceLock
from test_webapp import _queue


def mapping(ident='visit1', photos=None):
    return {'visit_id':ident, 'provider_id':'osm:node/1', 'name':'Lilia',
            'address':'567 Union Ave', 'photos':['a','b'] if photos is None else photos,
            'source':'photos','visit_date':'2026-11-01'}


def ready(w):
    w.approve([mapping(),mapping('visit2',[])])
    w.control('start')
    w.manual('visit1','identity',name='Lilia',address='567 Union Ave')
    w.manual('visit1','ranking')


def test_partial_photos_pause_stop_restart_and_no_repeated_confirmation(tmp_path):
    db=tmp_path/'l.sqlite'; led=Ledger(db); w=Worklist(led); ready(w)
    w.manual('visit1','photo','a')
    w.control('pause')
    with pytest.raises(ValueError): w.manual('visit1','photo','b')
    w.control('resume'); w.control('stop')
    with pytest.raises(ValueError): w.manual('visit1','finish')
    w.control('start')
    led.conn.close(); led=Ledger(db); w=Worklist(led)
    assert w.snapshot()['status']=='paused'
    v=w.snapshot()['current']
    assert v['ranking']=='user_confirmed'
    assert v['attachments']=={'a':'user_confirmed','b':'pending'}
    w.approve([mapping()])
    assert w.snapshot()['current']['attachments']==v['attachments']
    w.control('resume'); w.manual('visit1','photo','b'); w.manual('visit1','finish')
    assert w.snapshot()['current']['visit_id']=='visit2'
    assert w.snapshot()['visits'][0]['outcome']=='user_finished'
    with pytest.raises(ValueError): w.manual('visit1','photo','b') # stale page cannot affect next


def test_explicit_finish_without_photos_and_skip():
    w=Worklist(Ledger()); ready(w)
    w.manual('visit1','finish_without_photos')
    assert set(w.snapshot()['visits'][0]['attachments'].values())=={'waived_by_user'}
    w.manual('visit2','skip')
    assert w.snapshot()['current'] is None
    assert w.snapshot()['visits'][1]['outcome']=='skipped'


def test_batch_conflict_rolls_back_all_new_rows():
    w=Worklist(Ledger()); w.approve([mapping()])
    with pytest.raises(ValueError): w.approve([mapping('new'),mapping(photos=[])])
    assert len(w.snapshot()['visits'])==1


def test_legacy_rows_and_rollback_snapshot_preserved(tmp_path):
    db=tmp_path/'l.sqlite'; old=sqlite3.connect(db)
    old.execute('CREATE TABLE handled(place_id TEXT PRIMARY KEY,name TEXT,bucket TEXT,rating TEXT,action TEXT,ts TEXT)')
    old.execute("INSERT INTO handled VALUES ('old','Restaurant','been','loved','added','2025')");old.commit();old.close()
    led=Ledger(db); Worklist(led)
    before=led.conn.execute('SELECT * FROM handled').fetchall(); led.conn.close()
    led=Ledger(db); Worklist(led)
    assert led.conn.execute('SELECT * FROM handled').fetchall()==before
    snap=sqlite3.connect(str(db)+'.pre-assistant.bak')
    assert snap.execute('SELECT * FROM handled').fetchall()==before
    assert not snap.execute("SELECT 1 FROM sqlite_master WHERE name='assistant_visits'").fetchone()
    assert db.stat().st_mode & 0o077 == 0


def test_single_process_lock(tmp_path):
    with InstanceLock(tmp_path/'worker.lock'):
        with pytest.raises(RuntimeError):
            with InstanceLock(tmp_path/'worker.lock'): pass
    with InstanceLock(tmp_path/'worker.lock'): pass


def test_same_restaurant_separate_visits_have_separate_ids():
    a=_queue().been[0]; b=a.model_copy(deep=True)
    b.raw.photo_refs=['different']
    assert visit_id(a)!=visit_id(b)
    b.raw.photo_refs=list(reversed(a.raw.photo_refs))
    assert visit_id(a)==visit_id(b)
