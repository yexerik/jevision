import test from 'node:test';
import assert from 'node:assert/strict';
import {runFindAll} from '../web/tools/find/engine.js';
import {resolveV6Config, V6_DEFAULT_CONFIG} from '../web/tools/find/v6/config.js';
import {suppressFindDuplicates} from '../web/tools/find/v6/geometry.js';

function fixture(overrides={}, {countConfidence=.99,boxConfidence=.99,verification=.7,pair=false}={}) {
  let calls=0,closed=0;
  const runtime={v6Config:overrides,state:{},updateFindProgress(){},base64UrlSafeId:(()=>{let i=0;return()=>String(++i)})(),
    createImageBitmap:async()=>({width:800,height:800,close(){closed++}}),
    cropImageRegion:async(_,region)=>({blob:new Blob(['crop']),region,content:{left:0,top:0,right:1,bottom:1},width:280,height:280}),
    sendFindImageJudgment:async(request,uploads)=>{
      calls++;const answers={};
      for(const [key,q] of Object.entries(request.questions)) {
        if(q.type==='choice') {
          const same=key.endsWith('_same_object');
          const choice=same?'same':calls===1 && (key==='r0_multiplicity'||pair&&key==='r1_multiplicity')?'one':'none';
          answers[key]={choice,confidence:countConfidence,probabilities:{[choice]:same?.6:countConfidence}};
        } else if(q.type==='noul') answers[key]={noul:verification};
        else {
          let box={left:.2,top:.2,right:.6,bottom:.6};
          if(pair && ['r0_target_box','r1_target_box'].includes(key)) {
            const i=key.startsWith('r0')?0:1, region=uploads[i].region;
            const b=i?{left:.5,top:.18,right:.7,bottom:.32}:{left:.35,top:.18,right:.55,bottom:.32};
            box={left:(b.left-region.left)/(region.right-region.left),right:(b.right-region.left)/(region.right-region.left),
              top:(b.top-region.top)/(region.bottom-region.top),bottom:(b.bottom-region.top)/(region.bottom-region.top)};
          }
          answers[key]={box,confidence:boxConfidence};
        }
      }
      return {answers};
    }};
  return {run:()=>runFindAll({blob:new Blob(),content:{left:0,top:0,right:1,bottom:1}},'fixture','ants','v6',runtime),calls:()=>calls,closed:()=>closed};
}

test('V6 rejects unsupported or malformed settings before image/API work',async()=>{
  for(const config of [{minBoxConfidence:-.1},{duplicateBoxIou:1.01},{minChoiceConfidence:NaN},{minBoxConfidence:'0.5'},{maxRegions:999},[],null]) {
    const h=fixture(config);await assert.rejects(h.run(),/V6 setting/);assert.equal(h.calls(),0);assert.equal(h.closed(),0);
  }
});
test('V6 count-confidence and box-check controls affect actual search decisions',async()=>{
  const split=await fixture({}, {countConfidence:.2}).run();
  const accept=await fixture({minChoiceConfidence:.1},{countConfidence:.2}).run();
  assert.ok(split.checked>accept.checked);assert.equal(accept.boxes.length,1);
  const h=fixture({minBoxConfidence:1});const checked=await h.run();
  assert.equal(h.calls(),2);assert.equal(checked.boxes[0].verificationConfidence,.7);
});
test('V6 verification settings are isolated between concurrent runs and later defaults',async()=>{
  const overrides={minV3BoxCheckProbability:.6};
  const loose=fixture(overrides,{boxConfidence:.1}),strict=fixture({minV3BoxCheckProbability:.8},{boxConfidence:.1});
  const a=loose.run();overrides.minV3BoxCheckProbability=.99;
  const [accepted,rejected]=await Promise.all([a,strict.run()]);
  assert.equal(accepted.boxes.length,1);assert.equal(rejected.boxes.length,0);
  assert.equal(accepted.config.minV3BoxCheckProbability,.6);
  assert.equal((await fixture({}, {boxConfidence:.1}).run()).boxes.length,1);
  assert.equal(V6_DEFAULT_CONFIG.minV3BoxCheckProbability,.65);
});
test('V6 merge probability and duplicate IoU controls reach engine identity decisions',async()=>{
  const merged=await fixture({}, {pair:true}).run();
  const separate=await fixture({minDuplicatePairProbability:.8},{pair:true}).run();
  const geometric=await fixture({minDuplicatePairProbability:.8,duplicateBoxIou:.1},{pair:true}).run();
  assert.equal(merged.boxes.length,1);assert.equal(separate.boxes.length,2);assert.equal(geometric.boxes.length,1);
  const detections=[{box:{left:0,top:0,right:.6,bottom:.6}},{box:{left:.2,top:0,right:.8,bottom:.6}}];
  assert.equal(suppressFindDuplicates(detections,resolveV6Config({duplicateBoxIou:.4})).length,1);
  assert.equal(suppressFindDuplicates(detections,resolveV6Config({duplicateBoxIou:.8})).length,2);
});
