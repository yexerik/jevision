"""Dataset selection regression; uses a running local app, without model calls."""
import json
from pathlib import Path
import sys
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

BASE=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8877'
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    page.route('https://fonts.googleapis.com/**',lambda route:route.abort())
    page.route('https://fonts.gstatic.com/**',lambda route:route.abort())
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(BASE+'/tools/qa',wait_until='domcontentloaded')
    page.wait_for_function("document.querySelector('#layoutDataset')?.value==='design2code'")
    assert '484 pairs' in page.locator('#layoutDataset option:checked').inner_text()
    assert page.locator('#layoutDataset').is_enabled()
    assert page.locator('#layoutExample').is_enabled()
    assert page.locator('#layoutExample option').count()==485
    for identifier in ['001','484']:
        page.locator('#layoutExample').select_option(identifier)
        page.wait_for_function("id=>document.querySelector('#layoutStatus').textContent.startsWith('Loaded pair '+id)",arg=identifier)
        with urlopen(BASE+'/api/design2code/html?id='+identifier) as response:expected=json.load(response)['html']
        assert page.locator('#layoutHtml').input_value()==expected
        assert page.locator('#layoutReference').is_visible()
        page.wait_for_function("document.querySelector('#layoutReference').naturalWidth>0")
        assert page.locator('#layoutExample').is_enabled()
    page.locator('#downloadDesign2Code').click()
    page.wait_for_function("document.querySelector('#layoutDownloadStatus').textContent.includes('complete')")
    assert page.locator('#layoutExample').input_value()=='484'
    page.locator('#layoutDataset').select_option('')
    assert page.locator('#layoutExample').is_disabled()
    assert page.locator('#layoutReference').is_hidden()
    page.locator('#layoutDataset').select_option('design2code')
    assert page.locator('#layoutExample').is_enabled()
    page.locator('#layoutExample').select_option('001')
    page.wait_for_function("document.querySelector('#layoutStatus').textContent.startsWith('Loaded pair 001')")
    page.locator('#layoutRender').click()
    page.wait_for_function("document.querySelector('#layoutStatus').textContent.startsWith('Preview ready')",timeout=60000)
    assert page.locator('#layoutDataset').is_enabled()
    assert page.locator('#layoutExample').is_enabled()
    page.screenshot(path='/tmp/jev-layout-v3-dataset.png',full_page=True)
    page.locator('#layoutFile').set_input_files({'name':'example.html','mimeType':'text/html','buffer':b'<h1>Uploaded page</h1>'})
    page.wait_for_function("document.querySelector('#layoutHtml').value==='<h1>Uploaded page</h1>'")
    assert page.locator('#layoutDataset').input_value()==''
    assert page.locator('#layoutExample').is_disabled()
    assert page.locator('#layoutReference').is_hidden()
    # A status-service failure must not hide the already-downloaded dataset.
    page.route('**/api/design2code/status',lambda route:route.fulfill(status=503,json={'error':'Test status unavailable'}))
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("document.querySelector('#layoutDataset')?.value==='design2code'")
    assert page.locator('#layoutExample').is_enabled()
    page.locator('#layoutExample').select_option('484')
    page.wait_for_function("document.querySelector('#layoutStatus').textContent.startsWith('Loaded pair 484')")
    # No dataset must remain an explicit empty state, without enabling a dead picker.
    page.route('**/api/design2code/examples',lambda route:route.fulfill(json={'examples':[]}))
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("document.querySelector('#layoutDataset')?.textContent.includes('No downloaded datasets')")
    assert page.locator('#layoutDataset').is_disabled()
    assert page.locator('#layoutExample').is_disabled()
    assert not errors,errors
    print('PASS: 484 pairs, first/last pair loading, download refresh, manual input, render busy states, status failure, and empty dataset state.')
    browser.close()
