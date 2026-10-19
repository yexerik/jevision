"""Replay fixed V5 evidence; distinguish candidate coverage from acceptance losses.

Never invokes inference. Optional benchmark manifest supplies independent reference
boxes. Ant UI evidence alone supplies diagnostics, NOT measured accuracy.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
from scripts.score_boxes import score

ROOT=Path(__file__).resolve().parents[1]
POLICIES={'existing':{},'legacy-count-gate':{'aggregatePresence':False},'aggregate-presence':{'aggregatePresence':True},'relaxed':{'discoveryGate':.3,'presenceGate':.5,'sameGate':.6,'differentGate':.6}}


def analyze(source,out,allow_agent_labels=False):
    if out.exists():raise ValueError('Use a fresh output path')
    manifest=json.loads((source/'manifest.json').read_text())
    labels={c['id']:c['groundTruth'] for c in manifest['cases'] if 'groundTruth' in c}
    annotation=manifest.get('annotation') or {}
    agent=annotation.get('referenceKind')=='agent-visual' and annotation.get('independentOfDetectorOutputs') is True
    if labels and annotation.get('independent') is not True and not (allow_agent_labels and agent):
        raise ValueError('Independent annotation provenance required; agent exploration requires explicit opt-in')
    records=[];jobs=[];input_hashes={};identities=set()
    for path in sorted(source.glob('*.json')):
        run=json.loads(path.read_text())
        if not isinstance(run,dict):continue
        result=run.get('result') or run.get('evidence')
        if not result or result.get('evidenceVersion')!=2:continue
        if run.get('error') or run.get('pageErrors'):raise ValueError('Failed evidence run: '+path.name)
        identity=(run['case'],run['run'])
        if identity in identities:raise ValueError('Duplicate evidence identity')
        identities.add(identity)
        input_hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        for name,config in POLICIES.items():
            records.append({'case':run['case'],'run':run['run'],'policy':name,'truth':labels.get(run['case'])})
            jobs.append({'result':result,'config':config})
    expected={(c['id'],r) for c in manifest['cases'] for r in range(1,manifest.get('repeats',1)+1)}
    if not records or identities!=expected:raise ValueError('Incomplete or unexpected V5 evidence cohort')
    process=subprocess.run(['node',str(ROOT/'scripts/replay_find_evidence.mjs')],input=json.dumps(jobs),text=True,capture_output=True,check=True)
    replays=json.loads(process.stdout);rows=[]
    for record,replay in zip(records,replays,strict=True):
        truth=record.pop('truth');reasons=Counter(r for d in replay['decisions'] for r in d['reasons'])
        rows.append(record|{'counts':{k:len(v) for k,v in replay['stages'].items()},'reasons':dict(reasons),
             'missingVerification':replay['missingVerification'],'missingIdentity':replay['missingIdentity'],
             'iou50':{k:score(truth,v,.5) for k,v in replay['stages'].items()} if truth is not None else None})
    summaries={}
    for policy in POLICIES:
        items=[r for r in rows if r['policy']==policy];totals={}
        if labels:
            for stage in ['valid','discovery','verified','registered','located','review']:
                totals[stage]={key:sum(r['iou50'][stage][key] for r in items) for key in ['tp','fp','fn']}
                t=totals[stage];t['precision']=t['tp']/(t['tp']+t['fp']) if t['tp']+t['fp'] else 0;t['recall']=t['tp']/(t['tp']+t['fn']) if t['tp']+t['fn'] else 0
        reasons=Counter();[reasons.update(r['reasons']) for r in items]
        summaries[policy]={'runs':len(items),'stageIou50':totals or None,'reasons':dict(reasons),
          'missingVerification':sum(r['missingVerification'] for r in items),'missingIdentity':sum(r['missingIdentity'] for r in items)}
    report={'toolHashes':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['scripts/analyze_find_evidence.py','scripts/replay_find_evidence.mjs','scripts/score_boxes.py','web/tools/find/evidence.js','web/tools/find/registry.js','web/tools/find/identity-pairs.js','web/tools/find/geometry.js']},'sourceManifestSha256':hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),'inputHashes':input_hashes,
      'policies':POLICIES,'summary':summaries,'runs':rows,
      'scope':'Fixed discovery/check responses. Missing verification/identity remains unknown. Adaptive policy outcomes require separate live runs. Raw/review stages include duplicates and forced Box outputs on negatives; never interpret candidate recall alone as product accuracy.',
      'annotation':('Independent source labels' if annotation.get('independent') is True else 'Agent visual reference exploration; not independently human audited') if labels else 'No reference boxes; diagnostic counts only'}
    out.write_text(json.dumps(report,indent=2));print(json.dumps(summaries,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--allow-agent-labels',action='store_true')
    args=p.parse_args();analyze(args.source,args.out,args.allow_agent_labels)
