"""Live UI review of real ant photos. Calls Jev; NOT independently scored accuracy.

Uses the app's real library, controls, production HTTP transport and rendered boxes.
Preserves inputs, screenshots and multipart API exchanges without mocking inference.
Always use a fresh output directory; this review does not create reference labels.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import random
import sys
import time
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.benchmark_find import validate_v6_overrides
DEFAULT_CASES = ['0013035.jpg', '1225872729_6f0856588f.jpg', '150801171_cd86f17ed8.jpg',
                 '150801003_3390b73135.jpg', '424119020_6d57481dab.jpg']


def write(path, value):
    path.write_text(json.dumps(value, indent=2))


def run(base, out, versions, repeats, cases, dataset_id="hymenoptera/ants", labels=None, allow_agent_labels=False, pause_ms=0, v6_config=None):
    if out.exists():
        raise ValueError('Use a fresh output directory; keep previous UI evidence unchanged.')
    if not 0<=pause_ms<=5000:raise ValueError('pause_ms must be between zero and 5000')
    v6_config=validate_v6_overrides({} if v6_config is None else v6_config)
    references = json.loads(labels.read_text()) if labels else None
    if references:
        annotation=references.get('annotation',{})
        if annotation.get('independent') is not True and not (allow_agent_labels and annotation.get('referenceKind')=='agent-visual' and annotation.get('independentOfDetectorOutputs') is True):
            raise ValueError('Reference provenance is not eligible; explicitly allow agent visual references for exploratory scoring')
        if not cases:cases=[c['name'] for c in references['cases']]
    cases=cases or DEFAULT_CASES
    library = json.load(urlopen(base+'/api/library', timeout=60))
    dataset = next(d for d in library['datasets'] if d['id']==dataset_id)
    if references and any(c.get('target','ants')!=dataset['target'] for c in references['cases']):raise ValueError('Dataset target does not match reference class')
    selected = []
    for name in cases:
        index, image = next((i, p) for i,p in enumerate(dataset['images']) if p['name']==name)
        case={'id':Path(name).stem,'index':index,'image':image}
        if references:
            reference=next(c for c in references['cases'] if c['name']==name)
            case.update(id=reference['id'],groupId=reference['groupId'],stratum='absent' if not reference['groundTruth'] else 'single' if len(reference['groundTruth'])==1 else 'multiple',target='ants',groundTruth=reference['groundTruth'],referenceSha256=reference['sha256'])
        selected.append(case)
    out.mkdir(parents=True)
    for directory in ['inputs','screenshots','uploads','source']:(out/directory).mkdir()
    for case in selected:
        data=urlopen(base+case['image']['url'],timeout=30).read()
        destination=out/'inputs'/case['image']['name'];destination.write_bytes(data)
        case['sha256']=hashlib.sha256(data).hexdigest()
        if case.get('referenceSha256') and case['sha256']!=case['referenceSha256']:raise ValueError('Reference image hash mismatch')
    hashes={}
    for folder in ['web','dist']:
        for path in sorted((ROOT/folder).rglob('*')):
            if path.is_file() and path.suffix in ['.js','.css','.html']:
                relative=path.relative_to(ROOT);data=path.read_bytes()
                destination=out/'source'/relative;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
                hashes[str(relative)]=hashlib.sha256(data).hexdigest()
    runner=Path(__file__)
    runner_snapshot=out/'source/tests/browser_find_ants.py'
    runner_snapshot.parent.mkdir(parents=True,exist_ok=True);runner_snapshot.write_bytes(runner.read_bytes())
    hashes['tests/browser_find_ants.py']=hashlib.sha256(runner.read_bytes()).hexdigest()
    jobs=[(case,version,repeat) for case in selected for repeat in range(1,repeats+1) for version in versions]
    random.Random(20261018).shuffle(jobs)
    write(out/'manifest.json', {'purpose':'Live UI review; reference-relative exploratory scoring only' if references else 'Live UI qualitative review; no independent reference boxes, no precision/recall claim',
         'annotation':references['annotation'] if references else None,
         'referenceManifestSha256':hashlib.sha256(labels.read_bytes()).hexdigest() if labels else None,'pauseMs':pause_ms,
         'v6Config':v6_config,'base':base,'dataset':dataset['id'],'cases':selected,'versions':versions,'repeats':repeats,
         'model':'jev-1.14.0','sourceHashes':hashes,'concurrency':1,'seed':20261018,
         'schedule':[{'case':c['id'],'version':v,'run':r} for c,v,r in jobs]})
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1500,'height':1150},device_scale_factor=1)
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base+'/tools/find',wait_until='domcontentloaded')
        page.wait_for_function("(id)=>[...document.querySelector('#findDatasetSelect').options].some(o=>o.value===id)",arg=dataset_id,timeout=60000)
        page.locator('#findDatasetSelect').select_option(dataset['id'])
        page.locator('#findModeSelect').select_option('all')
        try:
            for case,version,repeat in jobs:
                if pause_ms:time.sleep(pause_ms/1000)
                name=f"{case['id']}-{version}-{repeat}"
                page.locator('#findPhotoSlider').focus()
                page.keyboard.press('Home')
                for _ in range(case['index']):page.keyboard.press('ArrowRight')
                page.locator('#findVersionSelect').select_option(version)
                if version=='v6' and v6_config:
                    page.locator('#findV6Settings').evaluate('(e)=>e.open=true')
                    for key,value in v6_config.items():page.locator('#findV6-'+key).fill(str(value*100))
                page.wait_for_function('(name)=>document.querySelector("#findPhotoStage .find-photo-caption")?.textContent===name',arg=case['image']['name'])
                page.locator('#findPhotoStage').screenshot(path=str(out/'screenshots'/f'{name}-before.png'))
                exchanges=[]
                def record(response):
                    if '/api/system-one' not in response.url:return
                    entry={'status':response.status}
                    try:entry['response']=response.json()
                    except Exception as error:entry['responseError']=str(error)
                    exchanges.append(entry)
                    write(out/f'{name}-http.json',exchanges)
                def record_failed(request):
                    if '/api/system-one' not in request.url:return
                    exchanges.append({'status':0,'networkError':request.failure})
                    write(out/f'{name}-http.json',exchanges)
                page.on('response',record)
                page.on('requestfailed',record_failed)
                errors.clear();started=time.perf_counter()
                page.locator('#findObjectButton').click()
                page.wait_for_function('!document.querySelector("#findObjectButton").disabled',timeout=300000)
                page.remove_listener('response',record)
                page.remove_listener('requestfailed',record_failed)
                result=page.evaluate('''() => ({
                    status:document.querySelector('#findObjectStatus').textContent,
                    error:document.querySelector('#findObjectStatus').classList.contains('error'),
                    boxes:[...document.querySelectorAll('.object-detection-box')].map(e=>({left:parseFloat(e.style.left)/100,top:parseFloat(e.style.top)/100,right:(parseFloat(e.style.left)+parseFloat(e.style.width))/100,bottom:(parseFloat(e.style.top)+parseFloat(e.style.height))/100})),
                    reviewBoxes:[...document.querySelectorAll('.review-detection-box')].map(e=>({left:parseFloat(e.style.left)/100,top:parseFloat(e.style.top)/100,right:(parseFloat(e.style.left)+parseFloat(e.style.width))/100,bottom:(parseFloat(e.style.top)+parseFloat(e.style.height))/100})),
                    evidence:document.querySelector('#findEvidenceData')?.textContent ? JSON.parse(document.querySelector('#findEvidenceData').textContent) : null,
                    config:document.querySelector('#findRunConfigData')?.textContent ? JSON.parse(document.querySelector('#findRunConfigData').textContent) : null,
                    clusters:document.querySelectorAll('.cluster-detection-box').length,
                    inspector:[...document.querySelectorAll('.find-api-exchange')].map(e=>{const p=e.querySelectorAll('pre');return {phase:e.querySelector('h3').textContent,request:JSON.parse(p[0].textContent),response:JSON.parse(p[1].textContent)};})
                })''')
                previews=page.evaluate("""async () => {
                  const images=[...document.querySelectorAll('.find-api-crop img')];
                  return await Promise.all(images.map(async img=>{
                    const blob=await (await fetch(img.src)).blob();
                    return await new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve({name:img.alt,data:reader.result});reader.readAsDataURL(blob);});
                  }));
                }""")
                for i,preview in enumerate(previews):
                    destination=out/'uploads'/f'{name}-{i+1}.jpg'
                    destination.write_bytes(base64.b64decode(preview['data'].split(',',1)[1]))
                result['uploadPreviews']=[{'name':p['name'],'path':f'uploads/{name}-{i+1}.jpg'} for i,p in enumerate(previews)]
                result.update(case=case['id'],version=version,run=repeat,seconds=time.perf_counter()-started,exchanges=exchanges,pageErrors=list(errors))
                write(out/f'{name}.json',result)
                page.locator('#findPhotoStage').screenshot(path=str(out/'screenshots'/f'{name}-after.png'))
                page.locator('#findObjectStatus').scroll_into_view_if_needed();page.screenshot(path=str(out/'screenshots'/f'{name}-ui.png'))
                print(json.dumps({k:result[k] for k in ['case','version','run','status','seconds']}|{'boxes':len(result['boxes']),'apiRequests':len(exchanges)}),flush=True)
                if result['error'] or errors:raise RuntimeError(f'UI run failed; evidence preserved: {name}')
        finally:browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8765')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--versions',nargs='+',choices=['v2','v4','v5','v6'],default=['v4','v5'])
    parser.add_argument('--repeats',type=int,default=1)
    parser.add_argument('--cases',nargs='+')
    parser.add_argument('--dataset',default='hymenoptera/ants')
    parser.add_argument('--labels',type=Path)
    parser.add_argument('--v6-config',type=Path,help='V6 gate overrides as probabilities from 0 to 1')
    parser.add_argument('--pause-ms',type=int,default=0,help='Delay between UI jobs for a paced live comparison')
    parser.add_argument('--allow-agent-labels',action='store_true',help='Explicit exploratory mode; does not certify references as independent/human audited')
    args=parser.parse_args();run(args.base,args.out,args.versions,args.repeats,args.cases,args.dataset,args.labels,args.allow_agent_labels,args.pause_ms,json.loads(args.v6_config.read_text()) if args.v6_config else None)
