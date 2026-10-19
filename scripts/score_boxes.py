"""One-to-one box scoring against frozen independent annotations.

Input: {"groundTruth": [{"left":0,"top":0,"right":1,"bottom":1}],
        "runs": [{"photo":"name", "version":"v1", "run":1, "boxes":[...]}]}
Use one input file per photo, with at least three runs per version.
"""
import argparse
from collections import Counter
import json
from pathlib import Path


def validate(box):
    values=[box[k] for k in ('left','top','right','bottom')]
    if not all(type(v) in (int,float) and 0 <= v <= 1 for v in values) or not (values[0]<values[2] and values[1]<values[3]):
        raise ValueError('Expected normalized, positive-area boxes.')


def iou(a,b):
    area=lambda r:(r['right']-r['left'])*(r['bottom']-r['top'])
    intersection=max(0,min(a['right'],b['right'])-max(a['left'],b['left']))*max(0,min(a['bottom'],b['bottom'])-max(a['top'],b['top']))
    return intersection/(area(a)+area(b)-intersection)


def score(truth,predictions,threshold):
    for box in truth+predictions: validate(box)
    # Maximum-cardinality bipartite matching: greedy IoU matching can lose TPs.
    edges=[[i for i,g in sorted(enumerate(truth),key=lambda item:-iou(p,item[1])) if iou(p,g)>=threshold] for p in predictions]
    owners={}
    def augment(p,seen):
        for g in edges[p]:
            if g in seen: continue
            seen.add(g)
            if g not in owners or augment(owners[g],seen):
                owners[g]=p
                return True
        return False
    tp=sum(augment(p,set()) for p in range(len(predictions)))
    fp=len(predictions)-tp; fn=len(truth)-tp
    precision=tp/len(predictions) if predictions else 0
    recall=tp/len(truth) if truth else 0
    matched=set(owners.values())
    duplicates=sum(bool(edges[p]) for p in range(len(predictions)) if p not in matched)
    return {'tp':tp,'fp':fp,'fn':fn,'precision':precision,'recall':recall,
            'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0,
            'duplicateCandidates':duplicates,'countError':len(predictions)-len(truth)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('input',type=Path);args=parser.parse_args()
    data=json.loads(args.input.read_text())
    if not data.get('annotation',{}).get('independent'):
        raise SystemExit('Record annotation.independent=true only for labels made without model overlays.')
    results=[]
    counts=Counter()
    for run in data['runs']:
        key=(run['version'],run['run'])
        if counts[key]: raise SystemExit('Duplicate version/run ID.')
        counts[key]+=1
        results.append({**{k:v for k,v in run.items() if k!='boxes'},'iou30':score(data['groundTruth'],run['boxes'],0.3),'iou50':score(data['groundTruth'],run['boxes'],0.5)})
    repeats={v:sum(k[0]==v for k in counts) for v in ('v1','v2','v3','v4')}
    print(json.dumps({'runs':results,'repeatCounts':repeats,'hasThreeRunsEach':all(n>=3 for n in repeats.values())},indent=2))


if __name__=='__main__':main()
