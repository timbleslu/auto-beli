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
