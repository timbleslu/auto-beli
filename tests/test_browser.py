"""Real Chromium tests, synthetic data only. Run after playwright install chromium."""
from pathlib import Path
import socket
import threading
import time

import pytest
import uvicorn
from playwright.sync_api import sync_playwright, expect
from beli_tool.webapp import create_app
from beli_tool.ledger import Ledger
from test_webapp import _queue

PAYLOAD = '&#39;);globalThis.__xss=true;//'


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        browser=p.chromium.launch(args=["--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding"])
        yield browser
        browser.close()


def test_original_attribute_decoding_exploit_is_reproduced(browser):
    page=browser.new_page()
    # Exact former arg() behavior, in an isolated synthetic page.
    vulnerable=PAYLOAD.replace('\\','').replace("'",'').replace('\n',' ')
    page.set_content('<script>function added(){}</script>' +
        '<button onclick="added(\'id\',\''+vulnerable+'\',\'been\',null)">Choose</button>')
    page.get_by_role('button',name='Choose').click()
    assert page.evaluate('globalThis.__xss') is True
    page.close()


@pytest.mark.parametrize('name',[
    PAYLOAD,
    '<img src=x onerror="globalThis.__xss=true">',
    'O’Malley’s "Café" — 東京 🍜 \\ \' & friends',
])
@pytest.mark.parametrize('enforce_csp',[True,False])
def test_dom_rendering_and_batch_approval_are_safe(browser,name,enforce_csp):
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    q=_queue(name=name,ident=PAYLOAD)
    q.been[0].match.address=name
    q.been[0].raw.photo_refs=['unsafe" onerror="globalThis.__xss=true']
    app=create_app(q,Ledger(),origin=origin)
    if not enforce_csp:
        @app.middleware('http')
        async def remove_csp(request,call_next):
            response=await call_next(request)
            del response.headers['content-security-policy']
            return response
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False,proxy_headers=False))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    deadline=time.monotonic()+5
    while not server.started and time.monotonic()<deadline: time.sleep(.01)
    assert server.started
    page=browser.new_page()
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    try:
        page.goto(origin)
        page.locator('#code').fill(app.state.pairing_code)
        page.get_by_role('button',name='Connect',exact=True).click()
        page.locator('#workspace').wait_for(state='visible')
        assert page.locator('#root h3').text_content()==name
        assert page.locator('#root select option').nth(1).text_content()==name+' — '+name
        page.get_by_label('Include this visit in the batch').check()
        page.get_by_label('Restaurant and branch').select_option(PAYLOAD)
        page.get_by_label('Approve this photo').check()
        page.get_by_role('button',name='Approve selected mappings').click()
        expect(page.get_by_role('status')).to_have_text('Batch approved and stored on this Mac.')
        expect(page.get_by_role('button',name='Start',exact=True)).to_be_enabled()
        with page.expect_response('**/api/control') as response:
            page.get_by_role('button',name='Start',exact=True).click()
        assert response.value.status == 200
        page.get_by_role('button',name='I checked this exact name and address in Beli').click()
        page.get_by_role('button',name='I checked that my ranking saved in Beli').click()
        # Pending attachment blocks finish; no false completion.
        page.get_by_role('button',name='Done — next restaurant (manual confirmation)').click()
        page.get_by_role('status').filter(has_text='Requested photos are still pending').wait_for()
        page.get_by_role('button',name='I checked this photo is saved on this restaurant').click()
        expect(page.locator('#current')).to_contain_text('Photo: user_confirmed')
        page.get_by_role('button',name='Done — next restaurant (manual confirmation)').click()
        page.locator('#worklist').filter(has_text='user_finished').wait_for()
        assert page.evaluate('globalThis.__xss === undefined')
        assert page.locator('[onclick],[onerror],[onchange]').count()==0
        assert not errors
    finally:
        page.close();server.should_exit=True;thread.join(timeout=5);sock.close()


def test_photo_first_discovery_keeps_selections_and_all_group_photos(browser):
    from test_discovery import assets, Provider, discovery_app
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    provider=Provider();app=discovery_app(provider=provider,photos=assets(9),origin=origin)
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False,proxy_headers=False))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    deadline=time.monotonic()+5
    while not server.started and time.monotonic()<deadline:time.sleep(.01)
    assert server.started
    page=browser.new_page()
    try:
        page.goto(origin);page.locator('#code').fill(app.state.pairing_code)
        page.get_by_role('button',name='Connect',exact=True).click()
        expect(page.locator('#discovery')).to_be_visible()
        expect(page.locator('#photo-grid .asset')).to_have_count(5)
        assert not provider.calls
        page.locator('#photo-grid input').first.check()
        page.get_by_label('Show photos').select_option('all')
        expect(page.locator('#photo-grid .asset')).to_have_count(9)
        expect(page.locator('#photo-grid input:checked')).to_have_count(1)
        for box in page.locator('#photo-grid input').all():box.check()
        page.get_by_role('button',name='Find restaurants for selected photos').click()
        expect(page.locator('#message')).to_contain_text('Visit ready')
        expect(page.locator('#root .photo')).to_have_count(9)
        expect(page.locator('#root .photo input:checked')).to_have_count(9)
        expect(page.locator('#photo-grid input:disabled')).to_have_count(9)
        page.get_by_label('Include this visit in the batch').check()
        page.get_by_label('Restaurant and branch').select_option('osm:node/1')
        # Correcting the restaurant cannot discard another draft choice or create
        # a second group from the same photos. Untrusted query text stays text.
        payload='<img src=x onerror="globalThis.__xss=true">'
        page.get_by_label('Wrong suggestions? Search restaurant name, city or address').fill(payload)
        page.get_by_role('button',name='Search this visit by name').click()
        expect(page.locator('#root h3')).to_have_text(payload)
        expect(page.locator('#root .photo input:checked')).to_have_count(9)
        expect(page.get_by_label('Include this visit in the batch')).to_be_checked()
        assert page.evaluate('globalThis.__xss === undefined')
        page.get_by_role('button',name='Approve selected mappings').click()
        expect(page.locator('#message')).to_have_text('Batch approved and stored on this Mac.')
        expect(page.locator('#worklist')).to_contain_text('O’Malley’s 東京')
        page.reload()
        expect(page.locator('#worklist')).to_contain_text('O’Malley’s 東京')
        expect(page.locator('#root .card')).to_have_count(0)
        assert len(provider.calls)==2
    finally:
        page.close();server.should_exit=True;thread.join(timeout=5);sock.close()


def test_missing_osm_restaurant_can_be_supplied_without_false_verification(browser):
    from test_discovery import assets, Provider, discovery_app
    class EmptyProvider(Provider):
        def result(self):return []
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    origin=f'http://127.0.0.1:{port}';provider=EmptyProvider()
    app=discovery_app(provider=provider,photos=assets(1),origin=origin)
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False,proxy_headers=False))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    deadline=time.monotonic()+5
    while not server.started and time.monotonic()<deadline:time.sleep(.01)
    assert server.started
    page=browser.new_page()
    try:
        page.goto(origin);page.locator('#code').fill(app.state.pairing_code)
        page.get_by_role('button',name='Connect',exact=True).click()
        page.locator('#photo-grid input').first.check()
        page.get_by_label('Restaurant name, city or address (optional)').fill('Missing restaurant, city')
        page.get_by_role('button',name='Find restaurants for selected photos').click()
        expect(page.locator('#message')).to_contain_text('Visit ready')
        expect(page.get_by_label('Include this visit in the batch')).to_be_disabled()
        page.locator('#root summary').click()
        name='Mắm \' & 東京';address='1 "<img src=x onerror=globalThis.__xss=true>" Street, City'
        page.get_by_label('Full restaurant name',exact=True).fill(name)
        page.get_by_label('Branch address and city',exact=True).fill(address)
        page.get_by_role('button',name='Use this restaurant for review').click()
        expect(page.locator('#root h3')).to_have_text(name)
        expect(page.locator('#root')).to_contain_text('not verified by OSM or Beli')
        expect(page.get_by_label('Include this visit in the batch')).to_be_enabled()
        page.get_by_label('Restaurant and branch').select_option(index=1)
        page.get_by_label('Include this visit in the batch').check()
        page.get_by_role('button',name='Approve selected mappings').click()
        expect(page.locator('#message')).to_have_text('Batch approved and stored on this Mac.')
        expect(page.locator('#worklist')).to_contain_text('ranking pending')
        assert len(provider.calls)==1  # user-supplied mapping made no provider request
        assert page.evaluate('globalThis.__xss === undefined')
    finally:
        page.close();server.should_exit=True;thread.join(timeout=5);sock.close()
