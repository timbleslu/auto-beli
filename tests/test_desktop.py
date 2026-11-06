from types import SimpleNamespace
from beli_tool.desktop import pair_when_ready


def test_pairing_secret_stays_out_of_browser_url_and_output(monkeypatch,capsys):
    calls=[];opened=[]
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*args): pass
    monkeypatch.setattr('beli_tool.desktop.socket.create_connection',lambda *a,**k:Connection())
    def run(args,**kwargs):
        calls.append((args,kwargs));return SimpleNamespace(returncode=0,stdout='button returned:Copy code')
    monkeypatch.setattr('beli_tool.desktop.subprocess.run',run)
    monkeypatch.setattr('beli_tool.desktop.webbrowser.open',opened.append)
    code='synthetic-pairing-secret'
    pair_when_ready('http://127.0.0.1:8000','127.0.0.1',code)
    assert opened==['http://127.0.0.1:8000']
    assert code in calls[0][0][-1]  # native local dialog only
    assert calls[1][0]==['pbcopy'] and calls[1][1]['input']==code
    assert not capsys.readouterr().out
