"""Score frozen real-UI runs against independent or explicitly agent-created references.

Agent mode is exploratory. It never upgrades annotation.independent/humanAudited.
Dashed review outlines and V4 cluster references remain outside individual counts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
from scripts.score_boxes import score
from scripts.benchmark_find import cohort_summary, paired_bootstrap, check_v6_result_config


def score_directory(source,out,allow_agent_labels=False):
    if out.exists():raise ValueError('Use a fresh report path')
    manifest=json.loads((source/'manifest.json').read_text());annotation=manifest.get('annotation') or {}
    independent=annotation.get('independent') is True
    agent=annotation.get('referenceKind')=='agent-visual' and annotation.get('independentOfDetectorOutputs') is True
    if not independent and not (allow_agent_labels and agent):raise ValueError('Independent references required unless agent exploratory mode is explicitly enabled')
    scope='Independent-reference development evaluation' if independent else 'Agent-created visual-reference exploration; not independently human-audited accuracy'
    rows=[]
    for case in manifest['cases']:
        truth=case['groundTruth'];image=(source/'inputs'/case['image']['name']).resolve()
        if not image.is_relative_to((source/'inputs').resolve()) or hashlib.sha256(image.read_bytes()).hexdigest()!=case['sha256']:
            raise ValueError('Frozen source image mismatch')
        for version in manifest['versions']:
            for repeat in range(1,manifest['repeats']+1):
                path=source/f"{case['id']}-{version}-{repeat}.json";run=json.loads(path.read_text())
                if (run['case'],run['version'],run['run'])!=(case['id'],version,repeat):raise ValueError('Run identity mismatch')
                if run.get('error') or run.get('pageErrors'):raise ValueError('Failed UI run retained; do not silently drop it')
                if version=='v6' and 'v6Config' in manifest:
                    check_v6_result_config(run.get('config'),manifest['v6Config'])
                tokens=0;unknown=0;failed=0
                for ex in run['exchanges']:
                    response=ex.get('response') or {};usage=response.get('usage') or {}
                    if 200<=ex['status']<300 and response.get('model')!=manifest['model']:raise ValueError('Model identity changed')
                    n=usage.get('input_tokens')
                    if type(n) is int and n>=0:tokens+=n
                    else:unknown+=1
                    failed+=not 200<=ex['status']<300
                reported=((run.get('evidence') or {}).get('budget') or {}).get('httpAttempts',max(len(run.get('inspector',[])),len(run['exchanges'])))
                if type(reported) is not int or reported<len(run['exchanges']):raise ValueError('HTTP accounting mismatch')
                missing=reported-len(run['exchanges']);unknown+=missing;failed+=missing
                rows.append({'case':case['id'],'groupId':case.get('groupId',case['id']),'target':case.get('target','ants'),'stratum':case.get('stratum','unspecified'),'version':version,'run':repeat,
                  'config':run.get('config'),'truth':len(truth),'predictions':len(run['boxes']),'iou50':score(truth,run['boxes'],.5),'iou30':score(truth,run['boxes'],.3),
                  'reviewIou50':score(truth,run.get('reviewBoxes',[]),.5),'reviewOutlines':len(run.get('reviewBoxes',[])),
                  'inputTokens':tokens,'unknownUsageAttempts':unknown,'failedAttempts':failed,'httpAttempts':reported,'seconds':run['seconds']})
    def summarize(items):
        result={}
        for threshold in ['iou50','iou30']:
            counts={key:sum(r[threshold][key] for r in items) for key in ['tp','fp','fn','duplicateCandidates']};tp,fp,fn=[counts[k] for k in ['tp','fp','fn']]
            result[threshold]=counts|{'precision':tp/(tp+fp) if tp+fp else 0,'recall':tp/(tp+fn) if tp+fn else 0,'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0}
        result.update(runs=len(items),inputTokens=sum(r['inputTokens'] for r in items),httpAttempts=sum(r['httpAttempts'] for r in items),unknownUsageAttempts=sum(r['unknownUsageAttempts'] for r in items),
          failedAttempts=sum(r['failedAttempts'] for r in items),medianSeconds=statistics.median(r['seconds'] for r in items),cohortSummary=cohort_summary(items))
        return result
    versions={}
    for version in manifest['versions']:
        items=[r for r in rows if r['version']==version]
        versions[version]=summarize(items)|{'repeats':{str(i):summarize([r for r in items if r['run']==i]) for i in range(1,manifest['repeats']+1)},
          'strata':{key:summarize([r for r in items if r['stratum']==key]) for key in sorted({r['stratum'] for r in items})}}
    report={'scope':scope,'annotation':annotation,'sourceManifestSha256':hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
      'scorerSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'dependencyHashes':{name:hashlib.sha256((Path(__file__).resolve().parent/name).read_bytes()).hexdigest() for name in ['score_boxes.py','benchmark_find.py']},'versions':versions,'runs':rows,
      'countScope':'Located individual boxes only. Review and cluster outlines excluded; no promotion or independent confirmation claim.'}
    if 'v6' in versions:report['v6PairedDifferences']={v:paired_bootstrap(rows,'v6',v) for v in versions if v!='v6'}
    if 'v5' in versions:report['pairedDifferences']={v:paired_bootstrap(rows,'v5',v) for v in versions if v!='v5'}
    out.write_text(json.dumps(report,indent=2));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--allow-agent-labels',action='store_true')
    a=p.parse_args();r=score_directory(a.source,a.out,a.allow_agent_labels);print(json.dumps({'scope':r['scope'],'versions':{v:d['iou50'] for v,d in r['versions'].items()}},indent=2))
