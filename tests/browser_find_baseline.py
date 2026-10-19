"""Live Find Objects baseline smoke test. Calls Jev; does not score accuracy.

Uses an ephemeral browser dataset and preserves inputs, source hash, and complete
API exchanges under .jev-image-data/find-baseline-2026-10-18 by default.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def ant_directory():
    from server import load_dotenv, photo_root
    load_dotenv()
    root=photo_root()
    for directory in [root/'hymenoptera/ants',root/'photos/ants',root/'ants']:
        if all((directory/name).is_file() for name in ['0013035.jpg','150801171_cd86f17ed8.jpg']):
            return directory
    raise RuntimeError('Ant fixtures are missing. Run python3 scripts/setup.py first.')


def run(base,out):
    ants=ant_directory()
    out.mkdir(parents=True,exist_ok=True);(out/'fixtures').mkdir(exist_ok=True)
    blank=out/'fixtures/empty.png';Image.new('RGB',(600,600),'white').save(blank)
    large=out/'fixtures/crowded-large.png'
    with Image.open(ants/'150801171_cd86f17ed8.jpg') as source:
        ImageOps.pad(source.convert('RGB'),(900,900),color='white').save(large)
    fixtures=[('empty',blank),('single',ants/'0013035.jpg'),('crowded-small',ants/'150801171_cd86f17ed8.jpg'),('crowded-large',large)]
    source=(ROOT/'web/app.js').read_bytes()
    manifest={'purpose':'Operational smoke test, not independently scored accuracy. One run per fixture/version.',
              'appSha256':hashlib.sha256(source).hexdigest(),
              'imageAssetsSha256':hashlib.sha256((ROOT/'web/image-assets.js').read_bytes()).hexdigest(),
              'controlsSha256':hashlib.sha256((ROOT/'web/index.html').read_bytes()).hexdigest(),
              'moduleHashes':{str(path.relative_to(ROOT/'web')):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((ROOT/'web').rglob('*.js'))},
              'model':'jev-1.14.0','versions':['v1','v2','v3','v4'],
              'fixtures':[{'id':name,'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for name,path in fixtures]}
    if (out/'manifest.json').exists() and json.loads((out/'manifest.json').read_text())!=manifest:
        raise RuntimeError('Baseline inputs/source changed; use a fresh output directory.')
    (out/'app.js').write_bytes(source)
    for name in manifest['moduleHashes']:
        destination=out/'modules'/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes((ROOT/'web'/name).read_bytes())
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    dataset={'id':'find-baseline-test','name':'Find baseline controls','target':'ants','createdAt':0,'storage':'workspace',
             'images':[{'id':name,'name':name+'.png','url':'/find-baseline-image/'+name,'results':[]} for name,_ in fixtures]}
    paths=dict(fixtures);rows=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport={'width':1440,'height':1100})
            page.route('https://fonts.googleapis.com/**',lambda route:route.abort())
            page.route('https://fonts.gstatic.com/**',lambda route:route.abort())
            page.route('**/api/library',lambda route:route.fulfill(json={'datasets':[dataset]}))
            page.route('**/find-baseline-image/*',lambda route:route.fulfill(body=paths[route.request.url.rsplit('/',1)[-1]].read_bytes(),content_type='image/png' if route.request.url.rsplit('/',1)[-1] in ('empty','crowded-large') else 'image/jpeg'))
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base+'/tools/find',wait_until='domcontentloaded')
            page.wait_for_function("[...document.querySelector('#findDatasetSelect').options].some(o=>o.value==='find-baseline-test')")
            page.locator('#findDatasetSelect').select_option('find-baseline-test')
            page.locator('#findModeSelect').select_option('all')
            assert page.locator('#findVersionSelect').input_value()=='v6'
            for index,(name,path) in enumerate(fixtures):
                page.locator('#findPhotoSlider').evaluate("(slider,value)=>{slider.value=String(value);slider.dispatchEvent(new Event('input',{bubbles:true}));}",index)
                for version in manifest['versions']:
                    destination=out/f'{name}-{version}.json'
                    # Resumable; failed runs are retried explicitly rather than cached.
                    if destination.exists():
                        previous=json.loads(destination.read_text())
                        if previous.get('verified'):
                            rows.append(previous);continue
                    page.locator('#findVersionSelect').select_option(version)
                    started=time.perf_counter()
                    page.locator('#findObjectButton').click()
                    page.wait_for_function("!document.querySelector('#findObjectButton').disabled",timeout=300000)
                    result=page.evaluate('''() => ({
                      status:document.querySelector('#findObjectStatus').textContent,
                      error:document.querySelector('#findObjectStatus').classList.contains('error'),
                      boxes:[...document.querySelectorAll('.object-detection-box')].map(e=>({left:parseFloat(e.style.left)/100,top:parseFloat(e.style.top)/100,right:(parseFloat(e.style.left)+parseFloat(e.style.width))/100,bottom:(parseFloat(e.style.top)+parseFloat(e.style.height))/100})),
                      clusters:document.querySelectorAll('.cluster-detection-box').length,
                      exchanges:[...document.querySelectorAll('.find-api-exchange')].map(e=>{const blocks=e.querySelectorAll('pre');return {phase:e.querySelector('h3').textContent,request:JSON.parse(blocks[0].textContent),response:JSON.parse(blocks[1].textContent)};})
                    })''')
                    result.update(fixture=name,version=version,seconds=round(time.perf_counter()-started,3),pageErrors=list(errors))
                    destination.write_text(json.dumps(result,indent=2))
                    print(json.dumps({key:result[key] for key in ['fixture','version','status','error','seconds']}),flush=True)
                    assert not result['error'],result['status']
                    assert not errors,errors
                    assert result['exchanges'],'No API request was sent.'
                    assert len(result['exchanges'])<=96,'Request budget exceeded'
                    assert all(item['response'].get('ok') for item in result['exchanges']), 'API error in exchange log'
                    for box in result['boxes']:
                        assert -1e-8<=box['left']<box['right']<=1+1e-8 and -1e-8<=box['top']<box['bottom']<=1+1e-8
                    first=result['exchanges'][0]['request']['request']
                    tile_ids=[key for key in first['state']['regions'] if key!='root']
                    expected=9 if version=='v3' and name=='crowded-large' else 4
                    assert len(tile_ids)==expected,(name,version,len(tile_ids))
                    if name=='empty':assert not result['boxes'],'False detection on empty control'
                    if version=='v4' and result['clusters']:
                        page.locator('.cluster-detection-box').first.click()
                        assert page.locator('#findClusterDetail').is_visible()
                        result['clusterZoomVerified']=True
                        destination.write_text(json.dumps(result,indent=2))
                    result['verified']=True
                    destination.write_text(json.dumps(result,indent=2))
                    rows.append(result)
                    if version=='v4' or (version=='v1' and name=='single'):
                        page.locator('#findPhotoStage').screenshot(path=str(out/f'{name}-{version}.png'))
            assert len(rows)==16
        finally:browser.close()
    summary={'manifest':manifest,'runs':[{key:value for key,value in row.items() if key!='exchanges'}|{'apiRequests':len(row['exchanges'])} for row in rows]}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print('PASS: all 16 live UI runs completed with expected initial grids and no JavaScript errors.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',default='http://127.0.0.1:8877');parser.add_argument('--out',type=Path,default=ROOT/'.jev-image-data/find-baseline-2026-10-18');args=parser.parse_args()
    run(args.base,args.out)
