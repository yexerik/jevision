"""Live browser smoke test; needs the local app and its TypeSafe API key."""
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8877'
OUT=Path('/tmp/jev-layout-tests'); OUT.mkdir(exist_ok=True)
CLEAN='''<!doctype html><style>body{margin:40px;font:20px Arial;color:#172333;background:#fff}table{border-collapse:collapse}td,th{padding:18px;border:1px solid #333}</style><h1>Quarterly sales</h1><p>Sales for the first two months.</p><table><tr><th>Month</th><th>Sales</th></tr><tr><td>January</td><td>120</td></tr><tr><td>February</td><td>140</td></tr></table>'''
BROKEN='''<!doctype html><style>body{margin:40px;font:24px Arial;color:#111;background:white}.clip{height:23px;width:140px;overflow:hidden;font-size:44px}.a,.b{position:absolute;left:50px;top:150px;font-size:70px;width:500px}.b{left:70px;top:175px;background:#f66}</style><h1 class="clip">Quarterly sales dashboard</h1><div class="a">Customer report: January February March April</div><div class="b">OVERLAPPING CONTENT BLOCKING THE REPORT</div>'''
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]; page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(BASE+'/tools/qa')
    page.wait_for_function("document.querySelector('#layoutExample').options.length === 485")
    assert page.locator('#qaView').is_visible()
    page.reload(); assert page.locator('#qaView').is_visible()
    page.locator('#layoutExample').select_option('001')
    page.wait_for_function("document.querySelector('#layoutHtml').value.length > 100 && !document.querySelector('#layoutValidate').disabled")
    assert page.locator('#layoutReference').is_visible()
    page.locator('#layoutRender').click()
    page.wait_for_function("document.querySelector('#layoutStatus').textContent.startsWith('Preview ready')",timeout=60000)
    assert page.locator('#layoutPreview').is_visible()
    page.screenshot(path=str(OUT/'dataset-preview.png'),full_page=True)
    # Clear reference before testing independent synthetic fixtures.
    page.locator('#layoutExample').select_option('')
    results=[]
    for name,html in ([] if '--ui-only' in sys.argv else [('clean',CLEAN),('broken',BROKEN)]):
        page.locator('#layoutHtml').fill(html)
        page.locator('#layoutOptionalChecks').evaluate('(details)=>details.open=true')
        page.locator('#layoutExpected').fill('a sales table')
        for run in range(1,4):
            page.locator('#layoutValidate').click()
            page.wait_for_function("!document.querySelector('#layoutValidate').disabled",timeout=150000)
            status=page.locator('#layoutStatus').inner_text()
            assert page.locator('#layoutExport').is_enabled(),status
            with page.expect_download() as info: page.locator('#layoutExport').click()
            path=OUT/f'{name}-{run}.json'; info.value.save_as(path)
            report=json.loads(path.read_text()); results.append({'fixture':name,'run':run,'summary':report['summary'],'answers':report['response']['answers']})
        page.screenshot(path=str(OUT/f'{name}.png'),full_page=True)
    page.locator('#layoutViewport').select_option('mobile')
    assert page.locator('#layoutExport').is_disabled()
    page.locator('#layoutRender').click()
    page.wait_for_function("document.querySelector('#layoutStatus').textContent.startsWith('Preview ready')",timeout=60000)
    assert page.locator('#layoutPreview').evaluate('(img)=>img.naturalWidth')==390
    page.locator('[data-view="home"]').first.click();page.go_back()
    assert page.locator('#qaView').is_visible()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile horizontal overflow'
    page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
    assert not errors,errors
    if results: (OUT/'summary.json').write_text(json.dumps(results,indent=2))
    print(json.dumps({'results':results,'pageErrors':errors},indent=2))
    browser.close()
