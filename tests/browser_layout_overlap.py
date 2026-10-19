"""Two live end-to-end regressions for layout-v3. Requires app/API key."""
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

BASE=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8877'
ROOT=Path(__file__).resolve().parents[1]
OUT=Path('/tmp/jev-layout-v3-ui');OUT.mkdir(exist_ok=True)
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    page.route('https://fonts.googleapis.com/**',lambda route:route.abort())
    page.route('https://fonts.gstatic.com/**',lambda route:route.abort())
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(BASE+'/tools/qa',wait_until='domcontentloaded')
    page.wait_for_function("document.querySelector('#layoutDataset')?.value==='design2code'")
    page.locator('#layoutDataset').select_option('')
    fixtures=[('clipped-heading',ROOT/'.jev-image-data/layout-overlap-confirmation-v2/html/confirmation-clipped-heading-mobile.html',False),('clipping-and-overlap',ROOT/'.jev-image-data/layout-mixed-regression-v3/html/regression-clipping-with-text-overlap-mobile.html',True)]
    for name,path,overlap in fixtures:
        page.locator('#layoutHtml').fill(path.read_text())
        page.locator('#layoutExpected').fill('a data table')
        page.locator('#layoutViewport').select_option('mobile')
        page.locator('#layoutValidate').click()
        page.wait_for_function("!document.querySelector('#layoutValidate').disabled",timeout=150000)
        assert page.locator('#layoutExport').is_enabled(),page.locator('#layoutStatus').inner_text()
        with page.expect_download() as event:page.locator('#layoutExport').click()
        destination=OUT/(name+'.json');event.value.save_as(destination)
        report=json.loads(destination.read_text())
        assert report['validatorVersion']=='layout-v3'
        assert report['thresholds']['overlapIssue']==.6
        raw=report['response']['answers']['overlap']
        assert raw['type']=='choice'
        probability=report['judgedProbabilities']['overlap']
        assert abs(probability-raw['probabilities']['overlap_only']-raw['probabilities']['both'])<1e-8
        assert (probability>=.6)==overlap,(name,probability)
        assert report['judgedProbabilities']['clipping']>=.7
        assert report['dataset'] is None
        assert page.locator('#layoutExample').is_disabled()
        print(name, 'overlap',probability,'clipping',report['judgedProbabilities']['clipping'])
    assert not errors,errors
    page.screenshot(path=str(OUT/'mixed-defect.png'),full_page=True)
    browser.close()
