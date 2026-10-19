import test from 'node:test';
import assert from 'node:assert/strict';
import { runFindAll } from '../web/tools/find/engine.js';
import { createFindRuntime } from '../web/tools/find/runtime.js';
import { V3_STRATEGY } from '../web/tools/find/v3.js';

// Exercise actual ES modules; replace only browser image and API I/O boundaries.
function harness(mode='empty') {
  const requests=[];
  let closed=0;
  let sequence=0;
  const runtime=createFindRuntime({
    base64UrlSafeId:()=>"test-"+(++sequence),
    createImageBitmap:async(blob)=>({width:blob.width,height:blob.height,close(){closed++;}}),
    sendFindImageJudgment:async(request,uploads)=>{
      requests.push({request,uploads});
      if(mode==='error')throw new Error('simulated service failure');
      const answers={};
      for(const [id,question] of Object.entries(request.questions)){
        if(question.type==='choice'){
          let choice='none';
          if(id==='root_multiplicity' && mode==='root-one')choice='one';
          if(id==='r0_multiplicity') {
            if(['one','weak-box'].includes(mode))choice='one';
            if(mode==='crowded')choice=requests.length===1?'two':'none';
            if(mode==='cluster')choice=requests.length===1?'two':'one';
          }
          const confidence=mode==='uncertain' && requests.length===1?.1:.99;
          answers[id]={type:'choice',choice,confidence,probabilities:{[choice]:confidence}};
        } else if(question.type==='box') {
          answers[id]={type:'box',confidence:mode==='weak-box'?.1:.99,box:{left:.2,top:.2,right:.6,bottom:.6}};
        } else answers[id]={type:'noul',noul:.99};
      }
      return {answers};
    },
  });
  runtime.cropImageRegion=async(bitmap,region)=>({blob:new Blob(["crop"]),content:{left:0,top:0,right:1,bottom:1},region:{...region},width:280,height:280});
  return {runtime,requests,closed:()=>closed,
    run:(version,width=600,height=600,content={left:0,top:0,right:1,bottom:1})=>runFindAll({blob:{width,height},content},'fixture','ants',version,runtime),
    strategy:()=>JSON.stringify(V3_STRATEGY),
  };
}

for(const version of ['v1','v2','v3','v4']){
  test(`${version}: empty image completes with the expected initial grid`,async()=>{
    const h=harness();const result=await h.run(version);
    assert.equal(result.version,version);assert.equal(result.boxes.length,0);
    assert.equal(result.unresolved,0);assert.equal(result.checked,4);
    assert.equal(result.apiRequests,1);assert.equal(h.closed(),1);
    assert.equal(Object.keys(h.requests[0].request.assets).length,['v3','v4'].includes(version)?5:4);
  });
  test(`${version}: single-target tile produces a valid detection`,async()=>{
    const h=harness('one');const result=await h.run(version);
    assert.equal(result.boxes.length,1);assert.equal(result.unresolved,0);
    assert.equal(result.apiRequests,version==='v1'?2:1);
    const box=result.boxes[0].box;
    assert.ok(box.left>=0&&box.top>=0&&box.right<=1&&box.bottom<=1);
    assert.ok(box.left<box.right&&box.top<box.bottom);
    assert.equal(h.closed(),1);
  });
  test(`${version}: service failure releases the bitmap`,async()=>{
    const h=harness('error');await assert.rejects(h.run(version),/simulated service failure/);
    assert.equal(h.closed(),1);
  });
}

test('V3 fallback uses unpadded content and does not mutate later large-image runs',async()=>{
  const h=harness();const original=h.strategy();
  const padded=await h.run('v3',800,800,{left:.1,top:.1,right:.9,bottom:.9});
  assert.equal(padded.checked,4);assert.equal(h.strategy(),original);
  const large=await h.run('v3',900,900);
  assert.equal(large.checked,9);assert.equal(h.strategy(),original);
  assert.equal(Object.keys(h.requests[1].request.assets).length,10);
});
test('V3 fallback boundary is below 220 pixels per proposed core',async()=>{
  assert.equal((await harness().run('v3',659,900)).checked,4);
  assert.equal((await harness().run('v3',660,660)).checked,9);
  assert.equal((await harness().run('v3',900,659)).checked,4);
});
test('V3 small-image fallback splits binary; large-image strategy splits quadrants',async()=>{
  assert.equal((await harness('crowded').run('v3',600,600)).checked,6);
  assert.equal((await harness('crowded').run('v3',900,900)).checked,13);
});
test('V2 and V4 retain their 2x2 initial grid on large images',async()=>{
  for(const version of ['v2','v4'])assert.equal((await harness().run(version,1200,900)).checked,4);
});
test('V4 keeps group references separate from individual detections',async()=>{
  const h=harness('cluster');const result=await h.run('v4',800,800);
  assert.equal(result.boxes.length,1);assert.equal(result.clusters.length,1);
  assert.equal(result.clusters[0].id,'C1');assert.equal(result.clusters[0].findings.length,1);
  assert.ok(result.clusters[0].previewBlob instanceof Blob);
});

test('unknown versions preserve the historical V1 fallback',async()=>{
  for(const version of ['unknown','toString','constructor']){
    assert.equal((await harness().run(version)).version,'v1');
  }
});

for (const mode of ['empty','one','root-one','weak-box','cluster','uncertain']) {
  test(`V6 initial fork preserves V4 requests and outcomes: ${mode}`,async()=>{
    const legacy=harness(mode), experimental=harness(mode);
    const before=await legacy.run('v4'), after=await experimental.run('v6');
    assert.equal(after.version,'v6');
    // Version identifiers in upload parts are the only expected request difference.
    const normalize=value=>JSON.parse(JSON.stringify(value).replaceAll('v6-','v4-'));
    assert.deepEqual(normalize(experimental.requests),normalize(legacy.requests));
    const {config,...outcome}=after;
    assert.equal(config.minV3BoxCheckProbability,.65);
    assert.deepEqual({...outcome,version:'v4'},before);
    assert.equal(experimental.closed(),1);
    if(mode==='weak-box')assert.equal(after.apiRequests,2,'Must exercise refinement');
    if(mode==='cluster')assert.equal(after.clusters.length,1,'Must retain cluster previews');
  });
}

test('V6 failure releases resources and does not affect subsequent V4 runs',async()=>{
  const failing=harness('error');
  await assert.rejects(failing.run('v6'),/simulated service failure/);
  assert.equal(failing.closed(),1);
  const legacy=await harness('one').run('v4');
  assert.equal(legacy.version,'v4');assert.equal(legacy.boxes.length,1);
});
