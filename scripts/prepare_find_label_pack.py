"""Freeze unseen ant/negative candidates for independent manual annotation.

Writes an offline canvas editor and draft labels. No model calls or predictions.
Folders are class labels, never reference boxes or certified negatives. Annotators
must audit target presence, visible body extent and source/scene grouping.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import random
from urllib.request import urlopen

PREVIOUS={'0013035.jpg','1225872729_6f0856588f.jpg','150801171_cd86f17ed8.jpg','150801003_3390b73135.jpg','424119020_6d57481dab.jpg'}

HTML='''<!doctype html><meta charset="utf-8"><title>Ant reference annotation</title>
<style>body{font:16px system-ui;margin:24px;max-width:1000px}canvas{display:block;width:100%;max-width:900px;background:#eee;touch-action:none}button,input,select{font:inherit;margin:8px 4px;padding:6px}#message{font-weight:bold}</style>
<h1>Ant reference annotation</h1><p>Draw one tight box per identifiable ant: head, thorax and abdomen together, excluding legs and antennae. Audit each original. A bee-folder photo may still contain an ant. No model predictions are shown.</p>
<p>Keep photos of the same scene in the same group. Assign whole groups to calibration or confirmation before using labels for tuning. This editor exports <strong>draft labels</strong>; a separate audit is required before accuracy scoring.</p>
<button id="prev">Previous</button><span id="position"></span><button id="next">Next</button><button id="undo">Undo box</button><button id="clear">Clear boxes</button>
<canvas id="canvas"></canvas><p id="name"></p>
<label>Scene group <input id="group"></label><label>Split <select id="split"><option>unassigned</option><option>calibration</option><option>confirmation</option></select></label>
<label><input type="checkbox" id="reviewed">Presence and every body box reviewed (empty boxes means an audited negative)</label>
<p><button id="export">Download draft annotations</button><span id="message"></span></p>
<script>
const pack=__PACK__;let index=0,start=null;const canvas=document.querySelector('#canvas'),ctx=canvas.getContext('2d'),img=new Image();
const cases=pack.cases.map(c=>({...c,groundTruth:[],reviewed:false,split:'unassigned'}));
function save(){const c=cases[index];c.groupId=document.querySelector('#group').value;c.split=document.querySelector('#split').value;c.reviewed=document.querySelector('#reviewed').checked;}
function draw(){ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0);ctx.strokeStyle='#e33212';ctx.lineWidth=Math.max(2,canvas.width/400);for(const b of cases[index].groundTruth)ctx.strokeRect(b.left*canvas.width,b.top*canvas.height,(b.right-b.left)*canvas.width,(b.bottom-b.top)*canvas.height);}
function show(){const c=cases[index];document.querySelector('#position').textContent=(index+1)+' / '+cases.length;document.querySelector('#name').textContent=c.name;document.querySelector('#group').value=c.groupId;document.querySelector('#split').value=c.split;document.querySelector('#reviewed').checked=c.reviewed;img.onload=()=>{canvas.width=img.width;canvas.height=img.height;draw();};img.src=c.data;}
function point(e){const r=canvas.getBoundingClientRect();return {x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))};}
canvas.onpointerdown=e=>{start=point(e);canvas.setPointerCapture(e.pointerId);};
canvas.onpointerup=e=>{if(!start)return;const p=point(e),b={left:Math.min(start.x,p.x),top:Math.min(start.y,p.y),right:Math.max(start.x,p.x),bottom:Math.max(start.y,p.y)};start=null;if(b.right>b.left&&b.bottom>b.top){cases[index].groundTruth.push(b);cases[index].reviewed=false;document.querySelector('#reviewed').checked=false;draw();}};
canvas.onpointercancel=()=>{start=null;};
document.querySelector('#prev').onclick=()=>{save();index=Math.max(0,index-1);show();};document.querySelector('#next').onclick=()=>{save();index=Math.min(cases.length-1,index+1);show();};
document.querySelector('#undo').onclick=()=>{cases[index].groundTruth.pop();cases[index].reviewed=false;document.querySelector('#reviewed').checked=false;draw();};document.querySelector('#clear').onclick=()=>{cases[index].groundTruth=[];cases[index].reviewed=false;document.querySelector('#reviewed').checked=false;draw();};
document.querySelector('#export').onclick=()=>{save();const result={...pack,cases:cases.map(({data,...c})=>c)};const blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='ant-labels-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);document.querySelector('#message').textContent='Draft exported. Independent review and scene grouping still required.';};show();
</script>'''


def prepare(base,out,count=24,negatives=6):
    if out.exists():raise ValueError('Use a fresh output directory')
    if count<1 or negatives<1:raise ValueError('Positive sample counts required')
    library=json.load(urlopen(base+'/api/library',timeout=60));rng=random.Random(20261018);selected=[]
    for dataset_id,n in [('hymenoptera/ants',count),('hymenoptera/bees',negatives)]:
        d=next(d for d in library['datasets'] if d['id']==dataset_id)
        available=[p for p in d['images'] if p['name'] not in PREVIOUS]
        for photo in rng.sample(available,n):selected.append((dataset_id,photo))
    out.mkdir(parents=True);(out/'images').mkdir();cases=[];seen=set()
    for dataset_id,photo in selected:
        data=urlopen(base+photo['url'],timeout=30).read();sha=hashlib.sha256(data).hexdigest()
        if sha in seen:raise ValueError('Duplicate source image; review selection')
        seen.add(sha);name=dataset_id.rsplit('/',1)[-1]+'-'+photo['name'];path='images/'+name;(out/path).write_bytes(data)
        cases.append({'id':sha[:16],'name':name,'target':'ants','path':path,'sha256':sha,'groupId':'REVIEW-'+sha[:12],
          'samplingFolder':dataset_id,'data':'data:image/jpeg;base64,'+base64.b64encode(data).decode()})
    pack={'annotation':{'independent':False,'status':'draft-unannotated','policy':'Ant head, thorax and abdomen together; exclude legs and antennae. No invented hidden extent.'},
      'selection':'Seeded random selection, excluding five previous UI originals. Folder labels are not ground truth. Scene independence/splits require human audit.',
      'seed':20261018,'cases':cases}
    (out/'annotate.html').write_text(HTML.replace('__PACK__',json.dumps(pack).replace('</','<\\/')))
    manifest={**pack,'cases':[{k:v for k,v in c.items() if k!='data'} for c in cases]}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({'photos':len(cases),'annotation':'unannotated draft','editor':str(out/'annotate.html')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',default='http://127.0.0.1:8765');p.add_argument('--out',type=Path,required=True);p.add_argument('--count',type=int,default=24);p.add_argument('--negatives',type=int,default=6)
    a=p.parse_args();prepare(a.base,a.out,a.count,a.negatives)
