import test from 'node:test';
import assert from 'node:assert/strict';
import { runFindAll } from '../web/tools/find/engine.js';
import { createFindRuntime } from '../web/tools/find/runtime.js';
import { resolveIdentities } from '../web/tools/find/registry.js';
import { withVisibleInstancePolicy } from '../web/tools/find/policy.js';

function harness({ config={}, missing=false, fail=false, badBox=false, crowded=false, unknownUsage=false }={}) {
  const calls=[], crops=[];
  let closed=0, sequence=0;
  const runtime=createFindRuntime({ v5Config:{rows:2,columns:2,maxRegions:64,maxDepth:4,refine:true,...config},
    base64UrlSafeId:()=>`fixture-${++sequence}`,
    createImageBitmap:async blob=>({width:blob.width,height:blob.height,close(){closed++;}}),
    cropImageRegion:async(bitmap,region,overlay)=>{
      crops.push({region,overlay,width:bitmap.width});
      return {blob:new Blob(['crop']),region:{...region},content:{left:0,top:0,right:1,bottom:1},width:280,height:280};
    },
    sendFindImageJudgment:async(request,uploads,phase)=>{
      calls.push({request,uploads,phase});
      if(fail) throw new Error('service unavailable');
      const answers={};
      for(const [key,q] of Object.entries(request.questions)) {
        if(missing) continue;
        if(q.type==='box') answers[key]={type:'box',box:{left:badBox?null:phase.endsWith('discover')?.4:.2,top:phase.endsWith('discover')?.4:.2,right:phase.endsWith('discover')?.6:.8,bottom:phase.endsWith('discover')?.6:.8},confidence:.99};
        else if(q.type==='choice') {
          const choice=key.endsWith('_identity')?'same':key==='r0_count' && calls.length===1?(crowded?'three_or_more':'one'):'none';
          answers[key]={type:'choice',choice,probabilities:{[choice]:.99},confidence:.99};
        } else answers[key]={type:'noul',noul:key.includes('_cut_')?.01:.99};
      }
      return {answers,...(unknownUsage?{}:{usage:{input_tokens:100,output_tokens:10}})};
    },
  });
  return {runtime,calls,crops,closed:()=>closed,
    run:prepared=>runFindAll(prepared||{blob:{width:600,height:600},content:{left:0,top:0,right:1,bottom:1}},'fixture','dogs','v5',runtime)};
}

test('V5 global single cannot cancel mandatory tile coverage; refinement can expand',async()=>{
  const h=harness();const r=await h.run();
  assert.equal(r.boxes.length,1);assert.equal(r.coverage.completed,4);assert.equal(r.coverage.complete,true);
  assert.equal(r.checked,5);assert.equal(r.apiRequests,3);assert.equal(h.closed(),1);
  assert.equal(r.observations.length,5);assert.equal(r.observations.filter(o=>o.discovery.pass).length,1);assert.notDeepEqual(r.observations[0].box,r.boxes[0].box);
  assert.ok(r.trace.some(t=>t.action==='refinement-proposed'));
  assert.equal(r.budget.inputTokens,300);
  // Each question sees exactly its own crop, not every image in shared state.
  assert.equal(h.calls[0].request.state.regions,undefined);
  for(const q of Object.values(h.calls[0].request.questions)) assert.ok(q.instructions.image);
});

test('V5 uses original pixels and maps outputs to the prepared image for display',async()=>{
  const h=harness();const r=await h.run({blob:{width:1568,height:800},sourceBlob:{width:4000,height:2000},content:{left:.1,top:.2,right:.9,bottom:.8}});
  assert.ok(h.crops.every(c=>c.width===4000));
  const d=r.boxes[0];assert.ok(d);
  assert.ok(Math.abs(d.preparedBox.left-(.1+d.box.left*.8))<1e-9);
  assert.ok(Math.abs(d.preparedBox.bottom-(.2+d.box.bottom*.6))<1e-9);
});

test('V5 missing answers cannot confirm a candidate or silently complete',async()=>{
  const h=harness({missing:true,config:{maxRegions:5}});const r=await h.run();
  assert.equal(r.boxes.length,0);assert.ok(r.unresolved>0);assert.equal(r.apiRequests,1);
  assert.ok(r.termination.includes('region-budget'));assert.equal(h.closed(),1);
});

test('V5 null box coordinates are invalid rather than coerced to zero',async()=>{
  const r=await harness({badBox:true}).run();assert.equal(r.observations.length,0);
  assert.ok(r.unresolved>0);
});

test('V5 request cap leaves candidates provisional',async()=>{
  const h=harness({config:{maxAttempts:1}});const r=await h.run();
  assert.equal(r.apiRequests,1);assert.equal(r.boxes.length,0);assert.equal(r.coverage.complete,true);
  assert.ok(r.unresolved>0);assert.equal(r.budget.stopped,'attempt-budget');
});

test('V5 token reserve stops discovery but permits verification with the reserve',async()=>{
  const r=await harness({crowded:true,config:{maxAttempts:4,reserveFraction:.75,maxRegions:64}}).run();
  assert.ok(r.boxes.length>0);assert.ok(r.unresolved>0);assert.ok(r.apiRequests<=4);
});

test('V5 failures and missing usage stop with honest accounting and release pixels',async()=>{
  for(const options of [{fail:true},{unknownUsage:true}]) {
    const h=harness(options);const r=await h.run();
    assert.equal(r.apiRequests,1);assert.equal(r.budget.unknownUsageAttempts,1);
    assert.equal(r.boxes.length,0);assert.ok(r.unresolved>0);assert.equal(h.closed(),1);
  }
});

test('V5 reports global/local contradictions rather than fabricating detections',async()=>{
  const r=await harness({crowded:true}).run();
  assert.equal(r.boxes.length,1);assert.ok(r.issues.some(i=>i.reason==='global-local-contradiction'));
  assert.ok(r.unresolved>0);
});

test('V5 rejects invalid loop and probability settings before decoding images',async()=>{
  for(const config of [{batchSize:0},{maxAttempts:NaN},{presenceGate:null},{contextFactor:0}]) {
    await assert.rejects(harness({config}).run(),/Invalid V5/);
  }
});

const box={left:0,top:0,right:.5,bottom:.5};
const observations=['A','B','C'].map(id=>({id,box,presence:.9,completeness:.9}));
test('Registry preserves different-instance constraints across same-instance chains',()=>{
  const r=resolveIdentities(observations,[{left:'A',right:'B',decision:'same'},{left:'B',right:'C',decision:'same'},{left:'A',right:'C',decision:'different'}]);
  assert.equal(r.objects.length,2);assert.equal(r.conflicts.length,1);assert.equal(r.unresolvedGroups,1);
  assert.ok(r.objects.every(o=>o.identityState==='uncertain'));
  assert.equal(observations.length,3);
  assert.equal(resolveIdentities(observations,[]).objects.length,3); // Reversible.
});
test('Registry counts connected uncertain groups separately from objects or pair edges',()=>{
  const r=resolveIdentities(observations,[{left:'A',right:'B',decision:'uncertain'},{left:'B',right:'C',decision:'uncertain'}]);
  assert.equal(r.unresolvedGroups,1);assert.equal(r.objects.length,3);
});
test('Policy controls preserve original requests and include visible extremities',()=>{
  const original={questions:{box:{type:'box',instructions:'exclude legs, antennae, other instances, the blue line, and background'}}};
  const revised=withVisibleInstancePolicy(original,'dogs');
  assert.ok(original.questions.box.instructions.startsWith('exclude legs'));
  assert.ok(revised.questions.box.instructions.includes('attached visible extremities'));
  assert.ok(!revised.questions.box.instructions.startsWith('exclude legs'));
});

test('V5 repeated service attempts debit their known input and output usage',async()=>{
  const h=harness({config:{maxAttempts:5,reserveFraction:0}});
  const send=h.runtime.sendFindImageJudgment;
  let first=true;
  h.runtime.delay=async()=>{};
  h.runtime.sendFindImageJudgment=async(...args)=>{
    if(first) {first=false;const e=new Error('temporarily unavailable');e.status=503;e.usage={input_tokens:50,output_tokens:5};throw e;}
    return send(...args);
  };
  const r=await h.run();
  assert.equal(r.apiRequests,4);assert.equal(r.budget.failedAttempts,1);
  assert.equal(r.budget.inputTokens,350);assert.equal(r.budget.outputTokens,35);
  assert.equal(r.budget.unknownUsageAttempts,0);assert.equal(r.boxes.length,1);
});

test('V5 budget before/after trace records each attempt and refuses ambiguous completeness',async()=>{
  const h=harness({config:{strictCompleteness:true}});
  const send=h.runtime.sendFindImageJudgment;
  h.runtime.sendFindImageJudgment=async(...args)=>{
    const r=await send(...args);
    for(const [id,a] of Object.entries(r.answers)) if(id.includes('_cut_'))a.noul=null;
    return r;
  };
  const r=await h.run();assert.equal(r.boxes.length,0);assert.ok(r.unresolved>0);
  const first=r.trace.find(t=>t.action==='request');
  assert.equal(first.before.httpAttempts,0);assert.equal(first.after.httpAttempts,1);
});

test('V5 distinguishes completed initial coverage from dense regions left unsearched',async()=>{
  const h=harness({config:{maxRegions:5}});
  const send=h.runtime.sendFindImageJudgment;
  h.runtime.sendFindImageJudgment=async(...args)=>{
    const r=await send(...args);
    if(args[2].endsWith('discover') && r.answers.r1_count) {
      r.answers.r1_count={type:'choice',choice:'three_or_more',confidence:.99,probabilities:{three_or_more:.99}};
    }
    return r;
  };
  const r=await h.run();
  assert.equal(r.coverage.complete,true);
  assert.equal(r.pendingRegions,4);
  assert.ok(r.termination.includes('region-budget'));
  assert.ok(r.unresolved>=4);
});

import { replayV5Evidence } from '../web/tools/find/evidence.js';

test('Fixed-response replay preserves gate-rejected boxes and never invents missing checks',async()=>{
  const h=harness({config:{refine:false,interleave:false,aggregatePresence:false}});
  const send=h.runtime.sendFindImageJudgment;
  h.runtime.sendFindImageJudgment=async(...args)=>{
    const r=await send(...args);
    if(args[2].endsWith('discover')) r.answers.r0_count.probabilities.one=.4;
    return r;
  };
  const r=await h.run();
  assert.equal(r.observations.length,5);assert.equal(r.boxes.length,0);
  assert.ok(r.acceptance.some(d=>d.reasons.includes('multiplicity-threshold')));
  const before=h.calls.length;
  const relaxed=replayV5Evidence(r,{discoveryGate:.3,presenceGate:.5});
  assert.equal(h.calls.length,before);assert.equal(relaxed.boxes.length,0);
  assert.ok(relaxed.missingVerification>0);
  assert.ok(relaxed.decisions[0].discovery);
});

test('Audit checks gate-rejected boxes, permitting measured threshold replay with explicit missing identity',async()=>{
  const h=harness({config:{refine:false,auditAllCandidates:true,interleave:false}});
  const send=h.runtime.sendFindImageJudgment;
  h.runtime.sendFindImageJudgment=async(...args)=>{
    const r=await send(...args);
    if(args[2].endsWith('discover')) r.answers.r0_count.probabilities.one=.4;
    return r;
  };
  const r=await h.run(),replay=replayV5Evidence(r,{discoveryGate:.3});
  assert.equal(r.boxes.length,0);assert.equal(replay.accepted.length,1);
  assert.equal(replay.missingVerification,0);assert.equal(replay.missingIdentity,1);
  assert.equal(replay.boxes.length,0);assert.equal(replay.reviewBoxes.length,1);
  assert.equal(replay.reviewBoxes[0].identityState,'unassessed');
});

test('Verified identity-uncertain instances remain review evidence and never inflate located counts',async()=>{
  const h=harness({config:{refine:false,interleave:false}});
  const send=h.runtime.sendFindImageJudgment;
  h.runtime.sendFindImageJudgment=async(...args)=>{
    const r=await send(...args);
    if(args[2].endsWith('discover')) {r.answers.r1_count={choice:'one',probabilities:{one:.99}};r.answers.r1_box.box={left:.7,top:.7,right:.95,bottom:.95};}
    if(args[2].endsWith('identity')) for(const a of Object.values(r.answers)) {a.choice='uncertain';a.probabilities={uncertain:.99};}
    return r;
  };
  const r=await h.run();assert.equal(r.boxes.length,0);assert.equal(r.reviewBoxes.length,2);
  assert.ok(r.acceptance.filter(d=>d.reasons.includes('identity-uncertain')).length===2);
  assert.equal(replayV5Evidence(r).reviewBoxes.length,2);
});

test('Adaptive follow-up searches run past minimum coverage and explicitly request new instances',async()=>{
  const h=harness({config:{refine:false,maxRegions:9,interleave:true,recoverDistinct:true}});
  const send=h.runtime.sendFindImageJudgment;
  h.runtime.sendFindImageJudgment=async(...args)=>{
    const r=await send(...args);
    if(args[2].endsWith('discover') && h.calls.filter(c=>c.phase.endsWith('discover')).length===1) {
      r.answers.r1_count={choice:'three_or_more',probabilities:{three_or_more:.99}};
      r.answers.r1_box.box={left:.3,top:.3,right:.5,bottom:.5};
    }
    return r;
  };
  const r=await h.run();assert.equal(r.checked,9);assert.equal(r.coverage.complete,true);
  const followup=h.calls.filter(c=>c.phase.endsWith('discover')).slice(1);
  assert.ok(followup.some(c=>Object.values(c.request.questions).some(q=>q.instructions.task.includes('ADDITIONAL physical instances'))));
  const phases=h.calls.map(c=>c.phase);
  assert.ok(phases.findIndex(p=>p.endsWith('verify'))<phases.lastIndexOf('V5 · discover'));
});

test('Replay refuses search changes and leaves unavailable multiplicity checks unassessed',async()=>{
  const r=await harness({config:{refine:false}}).run();
  assert.throws(()=>replayV5Evidence(r,{maxRegions:100}),/cannot change search/);
  assert.throws(()=>replayV5Evidence(r,{presenceGate:NaN}),/Invalid replay/);
  assert.throws(()=>replayV5Evidence(r,{strictCompleteness:'false'}),/Invalid replay/);
  const replay=replayV5Evidence(r,{rejectMultiple:true});
  assert.equal(replay.boxes.length,0);
  assert.ok(replay.decisions.some(d=>d.reasons.includes('multiplicity-check-not-run')));
});

test('Positional recovery retains separate raw attempts without inventing new identities',async()=>{
  const r=await harness({crowded:true,config:{refine:false,maxRegions:5,additionalPositions:true}}).run();
  assert.equal(r.checked,5);
  assert.ok(r.observations.some(o=>o.origin==='additional-leftmost'));
  assert.ok(r.observations.some(o=>o.origin==='additional-rightmost'));
  assert.equal(r.boxes.length,1); // Repeated localization is one instance, never a new count.
});

import { discoveryDecision } from '../web/tools/find/evidence.js';
test('Presence sums positive count alternatives instead of requiring certainty about the count',()=>{
  const uncertainCount={choice:'one',probabilities:{none:0,one:.48,two:.35,three_or_more:.17}};
  assert.equal(discoveryDecision(uncertainCount,.5,false).pass,false);
  const revised=discoveryDecision(uncertainCount,.5,true);
  assert.equal(revised.pass,true);assert.equal(revised.presenceProbability,1);
  assert.equal(discoveryDecision({choice:'none',probabilities:{none:.45,one:.25,two:.2,three_or_more:.1}},.5,true).pass,true);
  assert.equal(discoveryDecision({choice:'none',probabilities:{none:.95,one:.02,two:.02,three_or_more:.01}},.5,true).pass,false);
  assert.equal(discoveryDecision({choice:'one',probabilities:{none:null,one:.99}},.5,true).pass,false);
});

test('An uncertain positive count still gets verified, while a low verification score still rejects it',async()=>{
  for(const present of [.99,.2]) {
    const h=harness({config:{refine:false,aggregatePresence:true}}),send=h.runtime.sendFindImageJudgment;
    h.runtime.sendFindImageJudgment=async(...args)=>{
      const r=await send(...args);
      if(args[2].endsWith('discover')) r.answers.r0_count={choice:'one',probabilities:{none:0,one:.48,two:.35,three_or_more:.17}};
      if(args[2].endsWith('verify')) r.answers.r0_presence={noul:present};
      return r;
    };
    const r=await h.run();assert.equal(r.boxes.length,present===.99?1:0);
    assert.ok(r.observations[0].verification);assert.equal(r.observations[0].discovery.presenceProbability,1);
  }
});

test('Historical evidence retains the old count rule; presence replay cannot invent skipped verification',async()=>{
  const h=harness({config:{refine:false,aggregatePresence:false}}),send=h.runtime.sendFindImageJudgment;
  h.runtime.sendFindImageJudgment=async(...args)=>{
    const r=await send(...args);
    if(args[2].endsWith('discover')) r.answers.r0_count={choice:'one',probabilities:{none:0,one:.48,two:.35,three_or_more:.17}};
    return r;
  };
  const r=await h.run();delete r.config.aggregatePresence;
  assert.equal(replayV5Evidence(r).decisions[0].discovery,false);
  const changed=replayV5Evidence(r,{aggregatePresence:true});
  assert.equal(changed.decisions[0].discovery,true);assert.equal(changed.boxes.length,0);
  assert.ok(changed.decisions[0].reasons.includes('verification-not-run'));
});
