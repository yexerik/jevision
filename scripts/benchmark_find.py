"""Frozen COCO-label evaluation of the production Find Objects engine.

prepare downloads official validation annotations/images; run makes live API calls;
analyze scores completed runs. No labels are inferred from model predictions.
"""
import argparse
import asyncio
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import shutil
import math
from urllib.request import urlopen
from zipfile import ZipFile

from scripts.score_boxes import score, validate
from scripts.frontend_modules import freeze_modules, verify_modules

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / '.jev-image-data/find-coco-2026-10-18'
BUCKET = 'https://s3.amazonaws.com/images.cocodataset.org/'
VERSIONS = ['v1', 'v2', 'v3', 'v4']
SUPPORTED_VERSIONS = VERSIONS + ['v2-policy', 'v4-policy', 'v5', 'v6']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2))
    temp.replace(path)


def aggregate(items):
    totals = {k:sum(row[k] for row in items) for k in ['apiRequests','httpAttempts','failedAttempts','inputTokens','usdEstimate','clusters','unresolved']}
    for threshold in ['iou50','iou30']:
        counts = {k:sum(row[threshold][k] for row in items) for k in ['tp','fp','fn','duplicateCandidates']}
        tp,fp,fn = counts['tp'],counts['fp'],counts['fn']
        totals[threshold] = counts | {'precision':tp/(tp+fp) if tp+fp else 0, 'recall':tp/(tp+fn) if tp+fn else 0,
                                      'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0}
    latencies=sorted(row['seconds'] for row in items)
    totals.update(hardFailureRuns=sum(r.get('hardFailure',False) for r in items),
                  costComplete=all(not r.get('unknownCostAttempts',0) for r in items),
                  localizationReview=sum(r.get('localizationReview',0) for r in items),
                  medianSeconds=statistics.median(latencies),p95Seconds=latencies[max(0,math.ceil(.95*len(latencies))-1)],
                  unknownCostAttempts=sum(r.get('unknownCostAttempts',0) for r in items),
                  outputTokens=sum(r.get('outputTokens',0) for r in items),
                  coverageIncompleteRuns=sum(r.get('coverageIncomplete',False) for r in items),
                  budgetStoppedRuns=sum(r.get('budgetStopped',False) for r in items),
                  negativeImages=sum(r['truth']==0 for r in items),
                  negativeFalsePositiveRuns=sum(r['truth']==0 and r['predictions']>0 for r in items),
                  runs=len(items), meanSeconds=statistics.mean(row['seconds'] for row in items),
                  countMAE=statistics.mean(abs(row['predictions']-row['truth']) for row in items),
                  falseCompleteRuns=sum(row['unresolved']==0 and row['iou50']['fn']>0 for row in items))
    confirmed=[r['confirmedIou50'] for r in items if r.get('confirmedIou50') is not None]
    if confirmed:
        tp=sum(r['tp'] for r in confirmed);fp=sum(r['fp'] for r in confirmed);fn=sum(r['fn'] for r in confirmed)
        totals['confirmedIou50']={'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else 0,
                                  'recall':tp/(tp+fn) if tp+fn else 0}
    return totals


def cohort_summary(items):
    """Source-level uncertainty; repeats are never counted as new negatives."""
    groups=defaultdict(list)
    for i,row in enumerate(items):groups[row.get('groupId',row.get('case',str(i)))].append(row)
    negatives=[g for g in groups.values() if all(r['truth']==0 for r in g)]
    positive_negatives=sum(any(r['predictions']>0 for r in group) for group in negatives)
    n=len(negatives)
    interval=None
    if n:
        z=1.96;p=positive_negatives/n;den=1+z*z/n
        mid=(p+z*z/(2*n))/den;half=z*((p*(1-p)/n+z*z/(4*n*n))**.5)/den
        interval=[max(0,mid-half),min(1,mid+half)]
    categories=sorted({r['target'] for r in items})
    metrics=[]
    for target in categories:
        selected=[r for r in items if r['target']==target]
        tp=sum(r['iou50']['tp'] for r in selected);fp=sum(r['iou50']['fp'] for r in selected);fn=sum(r['iou50']['fn'] for r in selected)
        metrics.append({'target':target,'precision':tp/(tp+fp) if tp+fp else 0,'recall':tp/(tp+fn) if tp+fn else 0})
    return {'independentSourceGroups':len(groups),'negativeSourceGroups':n,
      'negativeGroupsWithAnyFalsePositive':positive_negatives,'negativeAnyRepeatFalsePositiveWilson95':interval,
      'macroCategoryIou50':{key:statistics.mean(m[key] for m in metrics) for key in ['precision','recall']} if metrics else None,
      'categoryMetrics':metrics,
      'interpretation':'Macro gives categories equal weight. Negative interval uses source groups with any-repeat FP; it is not a per-request or per-object error interval. Small groups and zero observed errors do not establish a low population error rate.'}


def attempt_usage(attempts):
    totals = {'inputTokens':0,'outputTokens':0,'unknownCostAttempts':0}
    for attempt in attempts:
        body=attempt.get('body') or {}
        usage=body.get('usage') or {}
        valid=lambda n:type(n) is int and n >= 0
        if valid(usage.get('input_tokens')):
            totals['inputTokens'] += usage['input_tokens']
        else:
            totals['unknownCostAttempts'] += 1
        if valid(usage.get('output_tokens')): totals['outputTokens'] += usage['output_tokens']
    return totals


def paired_bootstrap(rows, candidate, control, samples=2000, seed=20261018):
    """Resample source groups with every image/repeat kept together, never individual runs."""
    grouped=defaultdict(lambda:defaultdict(list))
    for row in rows:
        if row['version'] in (candidate,control): grouped[row.get('groupId',row['case'])][row['version']].append(row)
    if not grouped or any(set(g)!= {candidate,control} for g in grouped.values()):
        raise ValueError('Paired bootstrap needs both configurations in every group')
    for group in grouped.values():
        identities=lambda items:sorted((r['case'],r['run']) for r in items)
        if identities(group[candidate]) != identities(group[control]): raise ValueError('Unpaired image/repeat cohort')
    def metrics(items):
        tp=sum(r['iou50']['tp'] for r in items);fp=sum(r['iou50']['fp'] for r in items);fn=sum(r['iou50']['fn'] for r in items)
        return (tp/(tp+fp) if tp+fp else 0,tp/(tp+fn) if tp+fn else 0)
    groups=list(grouped.values()); rng=random.Random(seed); diffs=[[],[]]
    for _ in range(samples):
        chosen=rng.choices(groups,k=len(groups))
        a=metrics([r for g in chosen for r in g[candidate]])
        b=metrics([r for g in chosen for r in g[control]])
        for i in range(2): diffs[i].append(a[i]-b[i])
    actual_a=metrics([r for g in groups for r in g[candidate]])
    actual_b=metrics([r for g in groups for r in g[control]])
    return {'groups':len(groups),'samples':samples,'seed':seed,
            **{name:{'difference':actual_a[i]-actual_b[i],
                      'ci95':[sorted(diffs[i])[int(.025*(samples-1))],sorted(diffs[i])[int(.975*(samples-1))]]}
               for i,name in enumerate(['precision','recall'])}}


def prepare(out):
    if (out / 'manifest.json').exists():
        raise RuntimeError('Inputs already frozen; use run/analyze or a fresh output directory.')
    out.mkdir(parents=True, exist_ok=True)
    annotation = out / 'instances_val2017.json'
    if not annotation.exists():
        archive = out / 'annotations.zip'
        if not archive.exists():
            archive.write_bytes(urlopen(BUCKET + 'annotations/annotations_trainval2017.zip').read())
        with ZipFile(archive) as zipped:
            annotation.write_bytes(zipped.read('annotations/instances_val2017.json'))
    data = json.loads(annotation.read_text())
    images = {image['id']: image for image in data['images']}
    labels = defaultdict(list)
    for ann in data['annotations']:
        labels[ann['image_id'], ann['category_id']].append(ann)
    selected = []
    used = set()
    # Selection is deterministic, label-only, before any model output is available.
    # Keep all target boxes; exclude crowd and very small targets at selection time.
    for category, target in [(1, 'people'), (3, 'cars'), (18, 'dogs')]:
        for stratum, low, high in [('absent', 0, 0), ('single', 1, 1), ('sparse', 2, 3), ('crowded', 4, 6)]:
            candidates = []
            for image_id, image in images.items():
                truth = labels[image_id, category]
                if image_id in used or not low <= len(truth) <= high:
                    continue
                if any(a.get('iscrowd') or min(a['bbox'][2:]) < 20 or a['bbox'][2]*a['bbox'][3] < 900 for a in truth):
                    continue
                candidates.append(image_id)
            image_id = min(candidates, key=lambda key: digest(f'find-coco-v1:{category}:{stratum}:{key}'.encode()))
            used.add(image_id)
            image = images[image_id]
            path = out / 'images' / image['file_name']
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(urlopen(BUCKET + 'val2017/' + image['file_name'], timeout=60).read())
            boxes = []
            for ann in labels[image_id, category]:
                x, y, w, h = ann['bbox']
                boxes.append({'left':max(0, x/image['width']), 'top':max(0, y/image['height']),
                              'right':min(1, (x+w)/image['width']), 'bottom':min(1, (y+h)/image['height'])})
            selected.append({'id':f'{target}-{stratum}-{image_id}', 'imageId':image_id,
                             'categoryId':category, 'target':target, 'stratum':stratum,
                             'path':str(path.relative_to(out)), 'sha256':digest(path.read_bytes()),
                             'width':image['width'], 'height':image['height'], 'source':image,
                             'annotationIds':[a['id'] for a in labels[image_id, category]], 'groundTruth':boxes})
    for name in ['app.js', 'image-assets.js']:
        (out / name).write_bytes((ROOT / 'web' / name).read_bytes())
    manifest = {'annotation':{'independent':True, 'source':'COCO instances_val2017.json',
                             'url':BUCKET+'annotations/annotations_trainval2017.zip',
                             'sha256':digest(annotation.read_bytes())},
                'selection':'SHA256-ranked image IDs, seed find-coco-v1; category × 0/1/2–3/4–6 targets; no crowd, all target boxes at least 20px per side and 900px². No prediction-based selection.',
                'limitations':'Small development benchmark, not a held-out accuracy claim. COCO labels may omit unrecognizable instances/depictions. No tiny targets, insects or whales.',
                'versions':VERSIONS, 'repeats':3, 'model':'jev-1.14.0',
                'appSha256':digest((out/'app.js').read_bytes()),
                'imageAssetsSha256':digest((out/'image-assets.js').read_bytes()),
                'moduleHashes':freeze_modules(out, 'tools/find/engine.js'),
                'price':{'usdPerMillionInputTokens':0.042, 'outputTokensFree':True, 'source':'https://docs.typesafe.ai/models', 'checked':'2026-10-18', 'kind':'Published-rate estimate, not an invoice'},
                'cases':selected}
    write(out/'manifest.json', manifest)
    print(json.dumps({'frozen':len(selected), 'labels':sum(len(c['groundTruth']) for c in selected)}), flush=True)


V6_SETTING_KEYS=frozenset({'minChoiceConfidence','minBoxConfidence','minV3BoxCheckProbability','minDuplicatePairProbability','duplicateBoxIou'})

def validate_v6_overrides(config):
    if not isinstance(config,dict) or any(k not in V6_SETTING_KEYS or type(v) not in (int,float) or not 0 <= v <= 1 for k,v in config.items()):
        raise ValueError('Invalid V6 settings; use the five supported gates with probabilities from 0 to 1')
    return dict(config)


def check_v6_result_config(config,overrides):
    if not isinstance(config,dict) or not V6_SETTING_KEYS.issubset(config):
        raise ValueError('Missing effective V6 settings in result')
    validate_v6_overrides({k:config[k] for k in V6_SETTING_KEYS})
    if any(config.get(k)!=v for k,v in overrides.items()):
        raise ValueError('Effective V6 settings disagree with the frozen experiment')


def snapshot(out, source, versions, repeats=3, config=None, v6_config=None):
    """Freeze current code against an existing labeled cohort without changing history."""
    if out.exists():
        raise ValueError('Use a fresh snapshot directory; historical artifacts are immutable')
    v6_config=validate_v6_overrides({} if v6_config is None else v6_config)
    original = json.loads((source/'manifest.json').read_text())
    if original.get('annotation',{}).get('independent') is not True:
        raise ValueError('A labeled source with independent annotation provenance is required')
    if repeats < 1 or not versions or any(v not in SUPPORTED_VERSIONS for v in versions):
        raise ValueError('Invalid versions or repeats')
    if len(set(versions)) != len(versions):
        raise ValueError('Duplicate versions')
    # Validate every input before creating the output directory.
    for case in original['cases']:
        for box in case.get('groundTruth',[]): validate(box)
        path = (source/case['path']).resolve()
        if not path.is_relative_to(source.resolve()) or digest(path.read_bytes()) != case['sha256']:
            raise ValueError('Frozen input mismatch')
    out.mkdir(parents=True)
    manifest = dict(original)
    manifest.update(versions=versions, repeats=repeats, seed=20261018,
                    v5Config=config or {}, v6Config=v6_config, cohort='development-regression; reused sources, not independent confirmation',
                    sourceManifestSha256=digest((source/'manifest.json').read_bytes()),
                    policyVersion='visible-instance-v1', experiment=out.name,runProvenanceVersion=1)
    for case in original['cases']:
        destination = out/case['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/case['path'], destination)
    for name,key in [('app.js','appSha256'),('image-assets.js','imageAssetsSha256')]:
        shutil.copyfile(ROOT/'web'/name,out/name)
        manifest[key]=digest((out/name).read_bytes())
    manifest['moduleHashes']=freeze_modules(out,'tools/find/engine.js')
    manifest['harnessHashes']={}
    for relative in ['scripts/benchmark_find.py','scripts/score_boxes.py','scripts/frontend_modules.py']:
        data=(ROOT/relative).read_bytes()
        frozen=out/'harness'/relative
        frozen.parent.mkdir(parents=True,exist_ok=True);frozen.write_bytes(data)
        manifest['harnessHashes'][relative]=digest(data)
    audit=source/'label-audit.json'
    if audit.exists(): shutil.copyfile(audit,out/audit.name)
    # Live documentation checked before the experiment; keep historical rates untouched.
    manifest['price']={'usdPerMillionInputTokens':0.042,'outputTokensFree':True,
                       'source':'https://docs.typesafe.ai/models','checked':'2026-10-18',
                       'kind':'Published-rate estimate; failed attempts without usage have unknown cost'}
    write(out/'manifest.json',manifest)
    print(json.dumps({'snapshot':str(out),'versions':versions,'repeats':repeats}),flush=True)


# Replace only UI sinks; the algorithms, cropping, geometry, prompts and HTTP
# transport remain production code. Retries are logged, never replace predictions.
BRIDGE = '''
renderFindApiInspector = () => {};
updateFindProgress = () => {};
const benchmarkTransport = sendImageJudgment;
const benchmarkAttempts = [];
sendImageJudgment = async (request, uploads, endpoint, onResponse) => {
  for (let attempt=0; ; attempt++) {
    let responseRecord = null;
    const started = performance.now();
    try {
      return await benchmarkTransport(request, uploads, endpoint, response => {
        responseRecord = response;
        onResponse?.(response);
      });
    } catch(error) {
      if (window.benchmarkVersion === "v5" || attempt >= 3 || ![429, 502, 503, 504, 529].includes(responseRecord?.status)) throw error;
      await new Promise(resolve => setTimeout(resolve, 1000 * 2**attempt));
    } finally {
      benchmarkAttempts.push({status:responseRecord?.status, ok:responseRecord?.ok,
        body:responseRecord?.body, milliseconds:performance.now()-started});
    }
  }
};
window.runFindBenchmark = async ({url, id, target, version, config}) => {
  window.benchmarkVersion = version; window.benchmarkConfig = config;
  state.findApiLog = []; benchmarkAttempts.length = 0;
  const started = performance.now();
  let result = null, error = null;
  try {
    const blob = await (await fetch(url)).blob();
    const prepared = await prepareImage(blob, 1568, true);
    result = await findAllObjectsInImage(prepared, id, target, version);
  } catch(e) { error = String(e.stack || e); }
  const exchanges = state.findApiLog.map(entry => ({...entry,
    uploads: entry.uploads.map(({previewUrl, ...upload}) => upload)}));
  state.findApiLog.forEach(entry=>entry.uploads.forEach(upload=>URL.revokeObjectURL(upload.previewUrl)));
  return {result, error, seconds:(performance.now()-started)/1000, exchanges, attempts:[...benchmarkAttempts]};
};
'''


def benchmark_source(out, manifest):
    """Use modular engines for new snapshots; retain the historical app bridge."""
    if manifest.get('moduleHashes'):
        verify_modules(out, manifest['moduleHashes'])
        return '''
import { runFindAll } from "./modules/tools/find/engine.js";
import { createFindRuntime } from "./modules/tools/find/runtime.js";
import { prepareImage } from "./modules/image-assets.js";
import { sendImageJudgment as transport } from "./modules/api.js";
let sendImageJudgment = transport;
let renderFindApiInspector = () => {};
let updateFindProgress = () => {};
const state = { findApiLog: [] };
async function sendFindImageJudgment(request, uploads, phase) {
  const entry = {phase, sourcePhoto:"", request,
    uploads:uploads.map(({part, blob, name, width, height, region}) =>
      ({part, name, type:blob.type, sizeBytes:blob.size, width, height, region})),
    response:null, error:""};
  state.findApiLog.push(entry);
  try {
    return await sendImageJudgment(request, uploads, "/api/system-one", response => {entry.response=response;});
  } catch(error) {entry.error=error.message; throw error;}
}
function findAllObjectsInImage(prepared, id, target, version) {
  return runFindAll(prepared, id, target, version,
    createFindRuntime({state, sendFindImageJudgment, updateFindProgress, v5Config:window.benchmarkConfig, v6Config:window.benchmarkConfig}));
}
''' + BRIDGE
    source = (out/'app.js').read_text()
    source = source.replace('import { initLayout } from "./layout.js";', '')
    assert source.rstrip().endswith('init();')
    return source.rstrip()[:-len('init();')] + BRIDGE


def preflight_endpoint(base):
    """Do not turn an absent evaluation server into zero-detection model runs."""
    try:
        with urlopen(base.rstrip('/')+'/api/health',timeout=10) as response:
            health=json.load(response)
    except (OSError,ValueError) as error:
        raise RuntimeError('Evaluation endpoint unavailable; no live jobs started') from error
    if not isinstance(health,dict) or health.get('apiKeyConfigured') is not True:
        raise RuntimeError('Evaluation endpoint has no configured API key; no live jobs started')


async def run(out, base, workers):
    from playwright.async_api import async_playwright
    preflight_endpoint(base)
    manifest = json.loads((out/'manifest.json').read_text())
    for relative, expected in manifest.get('harnessHashes',{}).items():
        if digest((out/'harness'/relative).read_bytes()) != expected or digest((ROOT/relative).read_bytes()) != expected:
            raise ValueError('Benchmark harness changed; use a fresh snapshot for live runs')
    for name, key in [('app.js','appSha256'), ('image-assets.js','imageAssetsSha256')]:
        if digest((out/name).read_bytes()) != manifest[key]:
            raise RuntimeError('Frozen module hash mismatch')
    for case in manifest['cases']:
        if digest((out/case['path']).read_bytes()) != case['sha256']:
            raise RuntimeError('Frozen image hash mismatch')
    source = benchmark_source(out, manifest)
    jobs = [(case, version, repeat) for repeat in range(1, manifest.get('repeats',3)+1) for case in manifest['cases'] for version in manifest['versions']]
    random.Random(manifest.get('seed',20261018)).shuffle(jobs)  # Interleave versions/repeats against temporal drift.
    if workers < 1: raise ValueError('workers must be positive')
    manifest_hash=digest((out/'manifest.json').read_bytes())
    schedule = {'manifestSha256':manifest_hash,'workers':workers,'base':base,'jobs':[{'case':c['id'],'version':v,'run':r} for c,v,r in jobs]}
    schedule_path=out/'schedule.json'
    if schedule_path.exists() and json.loads(schedule_path.read_text()) != schedule:
        raise ValueError('Concurrency, endpoint or schedule changed; use a new snapshot')
    write(schedule_path,schedule)
    queue = asyncio.Queue()
    for case, version, repeat in jobs:
        destination = out/f"{case['id']}-{version}-{repeat}.json"
        if destination.exists():
            previous = json.loads(destination.read_text())
            if manifest.get('runProvenanceVersion') and previous.get('manifestSha256') != manifest_hash:
                raise ValueError('Run belongs to a different manifest')
            if previous.get('error') or previous.get('pageErrors'):
                raise RuntimeError(f'Failed run preserved at {destination}; resolve explicitly before resuming.')
            continue
        queue.put_nowait((case, version, repeat, destination))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        async def worker():
            page = await browser.new_page()
            await page.route('**/find-eval/runner', lambda route: route.fulfill(content_type='text/html', body='<script type="module" src="/find-eval/app.js"></script>'))
            await page.route('**/find-eval/app.js', lambda route: route.fulfill(content_type='text/javascript', body=source))
            await page.route('**/find-eval/image-assets.js', lambda route: route.fulfill(content_type='text/javascript', body=(out/'image-assets.js').read_bytes()))
            if manifest.get('moduleHashes'):
                async def serve_module(route):
                    name = route.request.url.split('/find-eval/modules/', 1)[1]
                    if name not in manifest['moduleHashes']:
                        await route.abort()
                        return
                    await route.fulfill(content_type='text/javascript', body=(out/'modules'/name).read_bytes())
                await page.route('**/find-eval/modules/**', serve_module)
            paths = {Path(c['path']).name:out/c['path'] for c in manifest['cases']}
            await page.route('**/find-eval/image/*', lambda route: route.fulfill(content_type='image/jpeg', body=paths[route.request.url.rsplit('/',1)[-1]].read_bytes()))
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.goto(base+'/find-eval/runner')
            await page.wait_for_function('typeof window.runFindBenchmark === "function"')
            while not queue.empty():
                case, version, repeat, destination = queue.get_nowait()
                result = await page.evaluate('args => window.runFindBenchmark(args)',
                    {'url':'/find-eval/image/'+Path(case['path']).name, 'id':case['id'], 'target':case['target'], 'version':version, 'config':manifest.get('v6Config',{}) if version=='v6' else manifest.get('v5Config',{})})
                result.update(case=case['id'], version=version, run=repeat, pageErrors=list(errors),manifestSha256=manifest_hash)
                write(destination, result)
                print(json.dumps({k:result[k] for k in ['case','version','run','seconds','error']} | {'boxes':len((result['result'] or {}).get('boxes',[]))}), flush=True)
                if result['error'] or errors:
                    raise RuntimeError(f'Benchmark failed: {destination}')
            await page.close()
        try:
            await asyncio.gather(*(worker() for _ in range(workers)))
        finally:
            await browser.close()


def analyze(out):
    manifest = json.loads((out/'manifest.json').read_text())
    rows = []
    for case in manifest['cases']:
        for version in manifest['versions']:
            for repeat in range(1,manifest.get('repeats',3)+1):
                path = out/f"{case['id']}-{version}-{repeat}.json"
                if not path.exists():
                    raise RuntimeError(f'Missing run: {path}')
                run = json.loads(path.read_text())
                hard_failure=bool(run.get('error') or run.get('pageErrors'))
                if manifest.get('runProvenanceVersion') and run.get('manifestSha256') != digest((out/'manifest.json').read_bytes()):
                    raise ValueError('Run manifest mismatch')
                result = run.get('result') or {'version':version,'boxes':[],'apiRequests':len(run.get('exchanges',[])),'unresolved':1,'coverage':{'complete':False}}
                if hard_failure: result={**result,'boxes':[],'unresolved':max(1,result['unresolved'])}
                if (run['case'], run['version'], run['run']) != (case['id'], version, repeat):
                    raise RuntimeError(f'Run identity mismatch: {path}')
                if result['version'] != version or result['apiRequests'] != len(run['exchanges']):
                    raise RuntimeError(f'Engine and exchange totals disagree: {path}')
                if any((a.get('body') or {}).get('model') != manifest['model'] for a in run['attempts'] if a.get('ok')):
                    raise RuntimeError('Model changed during evaluation')
                if version=='v6' and 'v6Config' in manifest and not hard_failure:
                    check_v6_result_config(result.get('config'),manifest['v6Config'])
                predictions = [b['box'] for b in result['boxes']]
                attempts = run['attempts']
                usage=attempt_usage(attempts)
                tokens=usage['inputTokens']
                rows.append({'case':case['id'], 'groupId':case.get('groupId',str(case.get('imageId',case['id']))), 'target':case['target'], 'stratum':case['stratum'], 'version':version, 'run':repeat,
                             'truth':len(case['groundTruth']), 'predictions':len(predictions), 'config':result.get('config'),
                             'iou50':score(case['groundTruth'],predictions,.5),
                             'confirmedIou50':score(case['groundTruth'],[b['box'] for b in result['boxes'] if b.get('localizationState')=='complete'],.5) if version=='v5' else None, 'iou30':score(case['groundTruth'],predictions,.3),
                             'clusters':len(result.get('clusters',[])), 'unresolved':result['unresolved'],
                             'apiRequests':len(run['exchanges']), 'httpAttempts':len(attempts),
                             'failedAttempts':sum(not a.get('ok') for a in attempts), 'inputTokens':tokens,
                             'unknownCostAttempts':usage['unknownCostAttempts'], 'outputTokens':usage['outputTokens'],
                             'hardFailure':hard_failure, 'error':run.get('error'),
                             'localizationReview':result.get('localizationReview',0),
                             'coverageIncomplete':not result.get('coverage',{}).get('complete',True),
                             'termination':result.get('termination',[]),
                             'budgetStopped':bool(result.get('budget',{}).get('stopped')),
                             'usdEstimate':tokens * manifest['price']['usdPerMillionInputTokens']/1_000_000,
                             'seconds':run['seconds']})
    versions = {}
    for version in manifest['versions']:
        items = [row for row in rows if row['version']==version]
        versions[version] = aggregate(items) | {'cohortSummary':cohort_summary(items),
            'repeats':{str(repeat):aggregate([r for r in items if r['run']==repeat]) for repeat in range(1,manifest.get('repeats',3)+1)},
            'strata':{stratum:aggregate([r for r in items if r['stratum']==stratum]) for stratum in sorted({r['stratum'] for r in items})},
            'targets':{target:aggregate([r for r in items if r['target']==target]) for target in sorted({r['target'] for r in items})}}
    report = {'analysisSha256':digest(Path(__file__).read_bytes()),'scorerSha256':digest((ROOT/'scripts/score_boxes.py').read_bytes()),'manifest':manifest, 'versions':versions, 'runs':rows,
              'duplicateDefinition':'Unmatched individual predictions with IoU >= threshold to a ground-truth object; subset of FP. Cluster boxes excluded.',
              'aggregation':f"Micro precision/recall across {len(manifest['cases'])} images × {manifest.get('repeats',3)} repeats per version. Repeats do not increase independent image count."}
    audit_path = out/'label-audit.json'
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        excluded = audit['excludedFromPolicyAlignedComparison']
        aligned = [row for row in rows if row['case'] not in excluded]
        report['labelAudit'] = audit
        report['policyAligned'] = {version:aggregate([row for row in aligned if row['version']==version]) | {'cohortSummary':cohort_summary([row for row in aligned if row['version']==version]),
            'repeats':{str(repeat):aggregate([r for r in aligned if r['version']==version and r['run']==repeat]) for repeat in range(1,manifest.get('repeats',3)+1)}
        } for version in manifest['versions']}
    if 'v6' in manifest['versions']:
        aligned=[row for row in rows if row['case'] not in report.get('labelAudit',{}).get('excludedFromPolicyAlignedComparison',[])]
        report['v6PairedDifferences']={control:paired_bootstrap(aligned,'v6',control) for control in manifest['versions'] if control!='v6'}
        report['v6Status']='Experimental V4-based development; no promotion claim.'
    if 'v5' in manifest['versions']:
        aligned=[row for row in rows if row['case'] not in report.get('labelAudit',{}).get('excludedFromPolicyAlignedComparison',[])]
        report['pairedDifferences']={control:paired_bootstrap(aligned,'v5',control) for control in manifest['versions'] if control!='v5'}
        candidate=report.get('policyAligned',versions)['v5']
        control=report.get('policyAligned',versions).get('v2-policy')
        report['gates']={
            'independentConfirmation':'incomplete; this is reused development data',
            'productPrecision90Recall80':'fail' if candidate['iou50']['precision'] < .9 or candidate['iou50']['recall'] < .8 else 'requires independent confirmation',
            'identityFalseMerges':'unscored; independent instance-association audit missing',
            'hardSlices':'incomplete; ants, whales, tiny/large-source quotas missing',
            'minimumCoverage':'pass' if candidate['coverageIncompleteRuns']==0 else 'fail',
            'serviceFailures':'pass' if candidate['hardFailureRuns']==0 and candidate['failedAttempts']==0 else 'fail',
            'usageComplete':'pass' if candidate['costComplete'] else 'unknown',
            'promotion':'not eligible',
            'scoreScope':'Displayed localized boxes include extent-review outputs; confirmed-only scores reported separately.'}
        if control:
            recall_delta=candidate['iou50']['recall']-control['iou50']['recall']
            precision_delta=candidate['iou50']['precision']-control['iou50']['precision']
            token_ratio=candidate['inputTokens']/control['inputTokens'] if control['inputTokens'] else None
            report['gates']['engineeringComparison']={
                'recallDelta':recall_delta,'precisionDelta':precision_delta,'tokenRatio':token_ratio,
                'status':'pass on displayed-box development metrics' if recall_delta>=.05 and precision_delta>=-.02 and token_ratio is not None and token_ratio<=2 else 'fail',
                'formalCalibrationGate':'not assessed on the required independent calibration set'}
        report['evaluationStatus']='Development only. Confirmation, identity audits and required hard-slice quotas are incomplete.'
    write(out/'summary.json',report)
    print(json.dumps(versions,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','snapshot','run','analyze'])
    parser.add_argument('--out',type=Path,default=DEFAULT)
    parser.add_argument('--base',default='http://127.0.0.1:8877')
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--source',type=Path,default=DEFAULT)
    parser.add_argument('--versions',nargs='+',choices=SUPPORTED_VERSIONS,default=['v2-policy','v4-policy','v5'])
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--v6-config',type=Path,help='Frozen V6 gate overrides as probabilities from 0 to 1')
    parser.add_argument('--config',type=Path,help='Frozen V5 configuration JSON for snapshot')
    args=parser.parse_args()
    if args.action=='prepare': prepare(args.out)
    elif args.action=='snapshot': snapshot(args.out,args.source,args.versions,args.repeats,json.loads(args.config.read_text()) if args.config else None,json.loads(args.v6_config.read_text()) if args.v6_config else None)
    elif args.action=='run': asyncio.run(run(args.out,args.base,args.workers))
    else: analyze(args.out)
