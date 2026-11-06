from datetime import date
import pytest
from beli_tool.config import load_config


def test_new_home_is_private_photos_only_osm_and_small(tmp_path, monkeypatch):
    monkeypatch.setattr('beli_tool.config.DEFAULT_HOME',tmp_path/'home')
    c=load_config()
    assert c.photos_only and c.provider=='osm' and c.max_visits==3
    assert 0 <= (c.until-c.since).days <= 7
    assert (tmp_path/'home').stat().st_mode & 0o077==0
    assert (tmp_path/'home/config.toml').stat().st_mode & 0o077==0


def test_optional_legacy_google_and_csv_are_explicit(tmp_path):
    path=tmp_path/'config.toml'
    path.write_text('google_places_api_key="key"\nphotos_only=false\nsaved_dir="~/inbox"\n')
    c=load_config(path)
    assert c.provider=='google' and c.api_key=='key' and not c.photos_only
    assert c.saved_dir.is_absolute()


def test_google_requires_key_and_env_is_supported(tmp_path, monkeypatch):
    p=tmp_path/'config.toml';p.write_text('provider="google"')
    monkeypatch.delenv('BELI_PLACES_KEY',raising=False)
    with pytest.raises(RuntimeError):load_config(p)
    monkeypatch.setenv('BELI_PLACES_KEY','key')
    assert load_config(p).api_key=='key'


@pytest.mark.parametrize('text',[
    'provider="bing"','max_visits=0','max_visits=21',
    'since="2020-01-01"\nuntil="2026-01-01"',
    'since="2026-11-05"\nuntil="2026-11-01"',
])
def test_invalid_configuration_fails(tmp_path,text):
    p=tmp_path/'config.toml';p.write_text(text)
    with pytest.raises(RuntimeError):load_config(p)


def test_quoted_and_bare_dates(tmp_path):
    p=tmp_path/'config.toml';p.write_text('since=2026-11-01\nuntil="2026-11-05"')
    c=load_config(p);assert c.since==date(2026,11,1) and c.until==date(2026,11,5)
