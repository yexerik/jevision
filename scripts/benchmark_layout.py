"""Render frozen fixtures, repeat live Jev checks, and measure held-out results.

prepare freezes labels and images without calling Jev. run resumes saved requests.
Only calibration groups are used to choose thresholds. No prompt tuning on heldout.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from layout_renderer import render
from scripts.layout_fixtures import fixtures, reference_fixtures, fresh_overlap_fixtures, overlap_regression_fixtures


def write(path,value):
    path.write_text(json.dumps(value,indent=2),encoding='utf-8')


def prepare(out,suite="initial",modules_from=None):
    if (out/'manifest.json').exists():raise SystemExit('Manifest already exists; use a fresh output directory.')
    out.mkdir(parents=True,exist_ok=True);(out/'images').mkdir(exist_ok=True);(out/'html').mkdir(exist_ok=True)
    if suite=='initial':cases=fixtures()+reference_fixtures(ROOT/'data/Design2Code-hf')
    elif suite=='overlap-confirmation':cases=fresh_overlap_fixtures()
    elif suite=='overlap-regression':cases=overlap_regression_fixtures()
    else:
        cases=[c for c in fixtures() if c['split']=='calibration']
        for case in cases:case['labels']={'overlap':case['labels']['overlap']};case['checks']=['overlap']
    for i,case in enumerate(cases,1):
        if 'html' in case:
            html=case.pop('html');(out/'html'/f"{case['id']}.html").write_text(html)
            image=out/'images'/f"{case['id']}.png";image.write_bytes(render(html,case['width'],case['height']));case['image']=str(image.resolve())
        case['imageSha256']=hashlib.sha256(Path(case['image']).read_bytes()).hexdigest()
        if 'reference' in case:case['referenceSha256']=hashlib.sha256(Path(case['reference']).read_bytes()).hexdigest()
        print(f"Prepared {i}/{len(cases)}",flush=True)
    manifest={'createdAt':datetime.now(timezone.utc).isoformat(),'labelMethod':'Synthetic construction and identity/different-page reference controls, frozen before Jev. Ambiguous cross-labels excluded. Agent-reviewed screenshots, not independent human labels.','repeats':3,'cases':cases}
    write(out/'manifest.json',manifest)
    if modules_from:
        (out/'modules').mkdir(exist_ok=True)
        for name in ('layout.js','image-assets.js'):(out/'modules'/name).write_bytes((modules_from/name).read_bytes())
    freeze_sources(out)


def freeze_sources(out):
    """Use the same production JS snapshots for every repeated request."""
    directory=out/'modules';directory.mkdir(exist_ok=True)
    for name in ('layout.js','image-assets.js'):
        path=directory/name
        if not path.exists():path.write_bytes((ROOT/'web'/name).read_bytes())
    lock={'manifestSha256':hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest(),
          'modules':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.glob('*.js'))}}
    path=out/'source-lock.json'
    if path.exists() and json.loads(path.read_text())!=lock:raise ValueError('Frozen source or manifest changed.')
    if not path.exists():write(path,lock)
    return lock


def run_case(case,run,out,base):
    from playwright.sync_api import sync_playwright
    target=out/'responses'/f"{case['id']}-r{run}.json"
    if target.exists():return json.loads(target.read_text())
    start=time.perf_counter()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            page=browser.new_page()
            page.route('**/bench-modules/*',lambda route:route.fulfill(body=(out/'modules'/route.request.url.rsplit('/',1)[-1]).read_bytes(),content_type='text/javascript'))
            page.route('**/bench-image/*',lambda route:route.fulfill(body=Path(case['reference'] if route.request.url.endswith('/reference') else case['image']).read_bytes(),content_type='image/png'))
            page.route('**/bench-runner', lambda route: route.fulfill(body='<!doctype html><html><body></body></html>', content_type='text/html'))
            page.goto(base+'/bench-runner')
            result=page.evaluate('''async ({expected, reference, fidelityOnly, checks}) => {
              const module=await import('/bench-modules/layout.js');
              const {buildLayoutRequest}=module;
              const {prepareImage}=await import('/bench-modules/image-assets.js');
              const request=buildLayoutRequest(expected,reference);
              if(fidelityOnly) request.questions={fidelity:request.questions.fidelity};
              if(checks) request.questions=Object.fromEntries(Object.entries(request.questions).filter(([id])=>checks.includes(id)));
              const form=new FormData();form.append('request',new Blob([JSON.stringify(request)],{type:'application/json'}));
              const images=[];
              for(const part of (reference?['rendered','reference']:['rendered'])){
                const input=await (await fetch('/bench-image/'+part)).blob();
                const blob=await prepareImage(input);
                form.append(part,blob,part+'.jpg');images.push({part,bytes:blob.size});
              }
              const started=performance.now();
              const response=await fetch('/api/system-one',{method:'POST',body:form});
              const payload=await response.json();
              if(!response.ok)throw new Error('API '+response.status+': '+JSON.stringify(payload));
              for(const id of Object.keys(request.questions)){
                const p=module.layoutProbability ? module.layoutProbability(payload.answers?.[id],id) : payload.answers?.[id]?.noul;
                if(typeof p!=='number'||!Number.isFinite(p)||p<0||p>1)throw new Error('Invalid answer: '+id);
              }
              return {request,response:payload,probabilities:Object.fromEntries(Object.keys(request.questions).map(id=>[id,module.layoutProbability ? module.layoutProbability(payload.answers[id],id) : payload.answers[id].noul])),images,apiSeconds:(performance.now()-started)/1000};
            }''',{'expected':case['expected'],'reference':'reference' in case,'fidelityOnly':case['kind']=='design2code-reference','checks':case.get('checks')})
        finally:browser.close()
    result.update(caseId=case['id'],run=run,elapsedSeconds=time.perf_counter()-start)
    write(target,result);return result


def run(out,base,workers,repeats):
    freeze_sources(out)
    manifest=json.loads((out/'manifest.json').read_text());(out/'responses').mkdir(exist_ok=True)
    # Verify frozen inputs, preventing changed screenshots from silently mixing runs.
    for case in manifest['cases']:
        for key in ('image','reference'):
            if key in case and hashlib.sha256(Path(case[key]).read_bytes()).hexdigest()!=case[key+'Sha256']:raise ValueError('Input changed: '+case['id'])
    failures=[]
    jobs=[(case,r) for r in range(1,repeats+1) for case in manifest['cases']]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending={pool.submit(run_case,c,r,out,base):(c['id'],r) for c,r in jobs}
        for i,future in enumerate(as_completed(pending),1):
            identifier,r=pending[future]
            try:result=future.result();print(f"{i}/{len(jobs)} {identifier} r{r}: {result['apiSeconds']:.2f}s",flush=True)
            except Exception as error:
                failures.append({'case':identifier,'run':r,'error':str(error)[:500]});print(f'FAILED {identifier} r{r}',flush=True)
    write(out/'failures.json',failures)
    if failures:raise SystemExit(f'{len(failures)} failed requests; rerun to resume.')


def reliability(samples):
    bins=[]
    for i in range(5):
        bucket=[(y,p) for y,p in samples if min(int(p*5),4)==i]
        if bucket:
            bins.append({'lower':i/5,'upper':(i+1)/5,'n':len(bucket),'meanProbability':statistics.mean(p for y,p in bucket),'positiveRate':statistics.mean(int(y) for y,p in bucket)})
    return {'bins':bins,'ece':sum(b['n']*abs(b['meanProbability']-b['positiveRate']) for b in bins)/len(samples) if samples else None}


def metrics(samples,threshold):
    tp=sum(y and p>=threshold for y,p in samples);fp=sum(not y and p>=threshold for y,p in samples)
    fn=sum(y and p<threshold for y,p in samples);tn=sum(not y and p<threshold for y,p in samples)
    return {'n':len(samples),'tp':tp,'fp':fp,'fn':fn,'tn':tn,'precision':tp/(tp+fp) if tp+fp else 0,'recall':tp/(tp+fn) if tp+fn else 0,'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0,'specificity':tn/(tn+fp) if tn+fp else 0,'brier':statistics.mean((p-int(y))**2 for y,p in samples) if samples else None}


def choose_threshold(samples,baseline=.7):
    # Predeclared objective: maximize balanced accuracy, then prefer fewer FP,
    # then proximity to the existing threshold. Grid fixed before heldout scoring.
    grid=[round(i/100,2) for i in range(10,96,5)]
    def key(t):
        m=metrics(samples,t)
        return ((m['recall']+m['specificity'])/2,-m['fp'],-abs(t-baseline))
    return max(grid,key=key)


def fit(out):
    """Freeze candidate thresholds using calibration responses only."""
    freeze_sources(out)
    manifest=json.loads((out/'manifest.json').read_text())
    samples={};hashes={}
    for case in manifest['cases']:
        if case['split']!='calibration':continue
        for r in range(1,manifest['repeats']+1):
            path=out/'responses'/f"{case['id']}-r{r}.json"
            raw=path.read_bytes();hashes[path.name]=hashlib.sha256(raw).hexdigest();row=json.loads(raw)
            for check,label in case['labels'].items():
                if label is not None:samples.setdefault(check,[]).append((label,row.get('probabilities',{}).get(check, row['response']['answers'][check].get('noul'))))
    if not samples:raise ValueError('No calibration labels here; analyze with --calibration pointing to the frozen calibration directory.')
    selection={'objective':'Maximize balanced accuracy on calibration single-run outputs; tie-break fewer FP then closest to 0.70. Fixed grid 0.10..0.95 step 0.05. Repeats are correlated, not independent new cases.',
               'thresholds':{check:choose_threshold(values) for check,values in samples.items()},'responseHashes':hashes}
    path=out/'calibration.json'
    if path.exists():
        existing=json.loads(path.read_text())
        if existing!=selection:raise ValueError('Calibration inputs changed after fitting. Use a new output directory.')
        return existing
    write(path,selection)
    return selection


def analyze(out,calibration=None):
    selection=fit(calibration or out)
    manifest=json.loads((out/'manifest.json').read_text())
    samples={split:{} for split in ('calibration','heldout')};by_case=[];latencies=[];usage={};models=set();prompt_hashes={}
    for case in manifest['cases']:
        runs=[json.loads((out/'responses'/f"{case['id']}-r{r}.json").read_text()) for r in range(1,manifest['repeats']+1)]
        for row in runs:
            latencies.append(row['apiSeconds']);models.add(row['response'].get('model'))
            for check,question in row['request']['questions'].items():
                prompt_hashes.setdefault(check,set()).add(hashlib.sha256(json.dumps(question,sort_keys=True).encode()).hexdigest())
            for k,v in row['response'].get('usage',{}).items():
                if type(v) in (float,int):usage[k]=usage.get(k,0)+v
        for check,label in case['labels'].items():
            if label is None:continue
            values=[row.get('probabilities',{}).get(check, row['response']['answers'][check].get('noul')) for row in runs]
            mean=statistics.mean(values)
            samples[case['split']].setdefault(check,[]).append((label,mean))
            by_case.append({'case':case['id'],'split':case['split'],'check':check,'label':label,'probabilities':values,'mean':mean,'range':max(values)-min(values)})
    thresholds=selection['thresholds']
    results={split:{check:{'baseline':metrics(values,.7),'candidate':metrics(values,thresholds.get(check,.7))} for check,values in checks.items()} for split,checks in samples.items()}
    # Additional single-run estimates avoid presenting mean-of-three accuracy as UI accuracy.
    single={split:{} for split in samples}
    for row in by_case:
        single[row['split']].setdefault(row['check'],[]).extend((row['label'],p) for p in row['probabilities'])
    summary={'method':'Thresholds fitted on calibration single-run outputs and frozen before heldout scoring; case means and single-run metrics both supplied. Repeats and viewport pairs are correlated.','promptHashes':{k:sorted(v) for k,v in prompt_hashes.items()},'cases':len(manifest['cases']),'requests':len(latencies),'models':sorted(models),'candidateThresholds':thresholds,'caseMeanMetrics':results,'singleRunMetrics':{split:{check:{'baseline':metrics(values,.7),'candidate':metrics(values,thresholds.get(check,.7))} for check,values in checks.items()} for split,checks in single.items()},'reliability':{split:{check:reliability(values) for check,values in checks.items()} for split,checks in single.items()},'repeatability':{'meanRange':statistics.mean(x['range'] for x in by_case),'maxRange':max(x['range'] for x in by_case)},'latency':{'medianSeconds':statistics.median(latencies),'p95Seconds':sorted(latencies)[int(.95*(len(latencies)-1))]},'usage':usage,'byCase':by_case}
    write(out/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='byCase'},indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run','fit','analyze']);parser.add_argument('--out',type=Path,default=ROOT/'.jev-image-data/layout-benchmark');parser.add_argument('--base',default='http://127.0.0.1:8877');parser.add_argument('--workers',type=int,default=4);parser.add_argument('--calibration',type=Path);parser.add_argument('--suite',choices=['initial','overlap-calibration','overlap-confirmation','overlap-regression'],default='initial');parser.add_argument('--modules-from',type=Path)
    args=parser.parse_args()
    if args.action=='prepare':prepare(args.out,args.suite,args.modules_from)
    elif args.action=='run':run(args.out,args.base,args.workers,3)
    elif args.action=='fit':print(json.dumps(fit(args.out),indent=2))
    else:analyze(args.out,args.calibration)


if __name__=='__main__':main()
