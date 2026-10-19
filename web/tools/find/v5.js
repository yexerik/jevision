/** Experimental V5: mandatory coverage, complete-instance refinement and auditable identity.
 * Configuration values are engineering candidates, not calibrated accuracy guarantees.
 */
import { createFindGridRegions, mapCropBoxToPreparedImage, mapBoxToPhoto, isValidBox,
  boxArea, boxIntersectionArea, paddedPairRegion } from "./geometry.js";
import { visibleInstancePolicy, FIND_POLICY_VERSION } from "./policy.js";
import { identityPairNeeded, pairKey, knownDifferent } from "./identity-pairs.js";
import { resolveIdentities } from "./registry.js";
import { discoveryDecision, verificationDecision, replayV5Evidence } from "./evidence.js";

export const V5_CONFIG = Object.freeze({
  rows:3, columns:3, halo:.18, maxDepth:2, maxRegions:10, batchSize:6,
  maxAttempts:96, maxInputTokens:100000, reserveFraction:.4,
  discoveryGate:.5, aggregatePresence:true, presenceGate:.75, completenessGate:.6,
  sameGate:.8, differentGate:.8, refinementIdentityGate:.8,
  contextFactor:2.5, refine:false, strictCompleteness:false,
  cleanRefinement:true, scopedImages:true,
  // Diagnostics and unvalidated search ablations; never silently enable them.
  auditAllCandidates:false, auditAllPairs:false, includeSourcePairs:false,
  skipKnownDifferent:false, rejectMultiple:false, verificationCountGate:.8,
  interleave:false, recoverDistinct:false, additionalPositions:false, maxAdditionalRegions:3,
});
const validBox = box => isValidBox(box) && ["left","top","right","bottom"].every(edge => typeof box[edge] === "number");
const UNIT = { left: 0, top: 0, right: 1, bottom: 1 };
const probability = value => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;
const chunks = (items, size) => Array.from({ length: Math.ceil(items.length / size) }, (_, i) => items.slice(i * size, (i + 1) * size));

export function contextRegion(box, width, height, factor = 2.5) {
  const cx = (box.left + box.right) / 2, cy = (box.top + box.bottom) / 2;
  const w = Math.max((box.right - box.left) * factor, 64 / width);
  const h = Math.max((box.bottom - box.top) * factor, 64 / height);
  return { left: Math.max(0, cx - w / 2), top: Math.max(0, cy - h / 2),
    right: Math.min(1, cx + w / 2), bottom: Math.min(1, cy + h / 2) };
}

function requestFor(items, target, phase, scopedImages, cleanRefinement, refine, auditCounts) {
  const regions = {}, assets = {}, questions = {};
  const policy = visibleInstancePolicy(target);
  items.forEach((item, i) => {
    const key = "r" + i, path = "`regions." + key + "`";
    regions[key] = item.reference;
    assets[item.reference] = { type: "image", part: item.part };
    const only = " Answer about " + path + " only. Ignore the other images. ";
    if (phase === "discover") {
      const extra = item.known?.length ? " The blue outlines identify previously located instances. Count and locate only ADDITIONAL physical instances distinct from all blue-outlined bodies. Do not return another part of an outlined body. " : "";
      questions[key + "_count"] = { type: "choice", instructions: "How many distinct identifiable real " + target + " are visible in " + path + "? Count partially occluded instances if identifiable. Exclude depictions, reflections, toys, shadows and unidentifiable fragments." + extra + only,
        criteria: { none: "Zero instances", one: "Exactly one instance", two: "Exactly two instances", three_or_more: "At least three instances" } };
      questions[key + "_box"] = { type: "box", instructions: "Locate one real " + target + " instance in " + path + ". If several are visible, choose the instance nearest the crop center. " + policy + extra + only };
    } else if (phase === "additional") {
      questions[key + "_box"] = {type:"box",instructions:"Locate the " + item.position + " identifiable real " + target + " body in " + path + ". Select ONE physical body by its center position, not a cluster or a disconnected body part. Return that instance’s complete visible extent. " + policy + only};
    } else if (phase === "refine") {
      questions[key + "_box"] = { type: "box", instructions: cleanRefinement ? "Locate the complete visible instance of " + target + " nearest the center of " + path + ". " + policy + only : "The red outline in " + path + " identifies a candidate instance of " + target + ". Locate that SAME instance's COMPLETE visible extent. The old outline may cut off parts or be loose: expand, shift or shrink it as needed. Never switch to a neighboring instance. " + policy + only };
    } else if (phase === "verify") {
      questions[key + "_presence"] = { type: "noul", instructions: "Is there an identifiable real " + target + " instance in " + path + "? Ignore reflections, depictions and toys." + only };
      if (auditCounts) questions[key + "_instance_count"] = { type:"choice", instructions:"How many distinct identifiable real " + target + " bodies are visible inside " + path + "? " + policy + " Separate touching bodies. A disconnected or unidentifiable fragment is not an additional instance." + only,
        criteria:{none:"No identifiable instance",one:"One identifiable instance",two:"Two distinct instances",three_or_more:"At least three distinct instances"} };
      for (const edge of ["left","top","right","bottom"]) {
        questions[key + "_cut_" + edge] = { type:"noul", instructions:"Does the " + target + " instance in " + path + " continue past the " + edge + " edge of this cropped image? " + policy + only };
      }
      questions[key + "_identity"] = { type: "choice", instructions: "Do the blue and red outlines identify the same physical " + target + " instance?",
        criteria: { same:"Same instance", different:"Different instances", uncertain:"Insufficient evidence" } };
    } else {
      questions[key + "_identity"] = { type: "choice", instructions: "Do the red and blue outlines in " + path + " identify the same physical " + target + " instance or different instances? Overlapping boxes alone do not establish identity. Different connected bodies are different instances, even when touching or occluded." + only,
        criteria: { same: "Same physical instance", different: "Two distinct instances", uncertain: "Cannot establish identity" } };
    }
  });
  if (phase === "verify" && !refine) items.forEach((item,i) => { delete questions["r"+i+"_identity"]; });
  if (phase === "verify" && refine) items.forEach((item,i) => {
    assets[item.identityReference] = { type:"image", part:item.identityPart };
    questions["r"+i+"_identity"].instructions = { image:item.identityReference, task:questions["r"+i+"_identity"].instructions };
  });
  if (scopedImages) {
    // Each question sees only its own crop. Multiple views in shared state can cause
    // Box answers to use another view's coordinate frame even with path instructions.
    items.forEach((item,i) => {
      const prefix = "r" + i + "_";
      for (const [key,q] of Object.entries(questions)) if (key.startsWith(prefix) && typeof q.instructions === "string") {
        q.instructions = { image: item.reference, task: q.instructions.replaceAll("`regions.r" + i + "`", "`image`") };
      }
    });
  }
  return { model: "jev-1.14.0", state: scopedImages ? { policy: FIND_POLICY_VERSION } : { regions }, assets, questions };
}

export async function findAllObjectsV5(prepared, imageId, target, runtime) {
  const config = { ...V5_CONFIG, ...runtime.v5Config };
  // Reject impossible settings rather than allowing an infinite loop or an unbounded run.
  for (const name of ["rows", "columns", "maxDepth", "maxRegions", "maxAdditionalRegions", "batchSize", "maxAttempts", "maxInputTokens"])
    if (!Number.isInteger(config[name]) || config[name] < 1) throw new Error("Invalid V5 configuration: " + name);
  for (const name of ["verificationCountGate", "discoveryGate", "presenceGate", "completenessGate", "sameGate", "differentGate", "refinementIdentityGate", "reserveFraction", "halo"])
    if (probability(config[name]) === null) throw new Error("Invalid V5 configuration: " + name);
  for (const name of ["refine","strictCompleteness","cleanRefinement","scopedImages","aggregatePresence","additionalPositions","auditAllCandidates","auditAllPairs","includeSourcePairs","skipKnownDifferent","rejectMultiple","interleave","recoverDistinct"])
    if (typeof config[name] !== "boolean") throw new Error("Invalid V5 configuration: " + name);
  if (config.rows * config.columns > 255 || config.maxRegions > 255 || config.batchSize > 16 || config.maxAttempts > 192 || config.maxInputTokens > 200000 || config.reserveFraction >= 1)
    throw new Error("Invalid V5 engineering limits");
  if (!validBox(prepared.content)) throw new Error("Invalid V5 prepared-image transform");
  if (!Number.isFinite(config.contextFactor) || config.contextFactor < 1) throw new Error("Invalid V5 context factor");
  const bitmap = await runtime.createImageBitmap(prepared.sourceBlob || prepared.blob, { imageOrientation: "from-image" });
  const root = prepared.sourceBlob ? { ...UNIT } : { ...prepared.content };
  const phaseUsage = {discoveryAttempts:0, discoveryInputTokens:0};
  const trace = [], observations = [], accepted = [], relationships = [], issues = [], geometryRejections = [];
  const processedObservations = new Set(), comparedPairs = new Set(), additionalRegions = [];
  const budget = { httpAttempts: 0, inputTokens: 0, outputTokens: 0, unknownUsageAttempts: 0, failedAttempts: 0, stopped: null };
  let checked = 0, globalMinimum = 0, minimumChecked = 0;
  let estimateRatio = 1;
  const addTrace = (action, details = {}) => trace.push({ sequence: trace.length + 1, action, ...details });
  const parent = { core: root, crop: root, depth: 0 };
  const minimum = createFindGridRegions(parent, config.rows, config.columns, config.halo, bitmap.width, bitmap.height);
  const queue = [{ ...parent, global: true }, ...minimum.map(r => ({ ...r, minimum: true }))];
  const expectedMinimum = config.rows * config.columns;
  if (minimum.length !== expectedMinimum) issues.push({ reason: "coverage-layout-too-small", missing: expectedMinimum - minimum.length });
  async function item(region, overlay = null) {
    const crop = await runtime.cropImageRegion(bitmap, region, overlay);
    return { crop, reference: runtime.base64UrlSafeId(), part: "v5-" + runtime.base64UrlSafeId() };
  }
  async function send(items, phase, discovery = false) {
    const request = requestFor(items, target, phase, config.scopedImages, config.cleanRefinement, config.refine, config.auditAllCandidates || config.rejectMultiple);
    const uploads = items.flatMap(i => [
      { part:i.part,blob:i.crop.blob,name:i.part+".jpg",width:i.crop.width,height:i.crop.height,region:i.crop.region },
      ...(i.identityCrop ? [{part:i.identityPart,blob:i.identityCrop.blob,name:i.identityPart+".jpg",width:i.identityCrop.width,height:i.identityCrop.height,region:i.identityCrop.region}] : [])
    ]);
    const estimate = Math.ceil((JSON.stringify(request).length / 3 + uploads.reduce((s,u) => s + Math.max(256, u.width * u.height / 400), 0)) * estimateRatio);
    const ceiling = discovery ? config.maxInputTokens * (1 - config.reserveFraction) : config.maxInputTokens;
    const attemptsCeiling = discovery ? Math.max(1, Math.floor(config.maxAttempts * (1 - config.reserveFraction))) : config.maxAttempts;
    for (let retry = 0; retry < 4; retry++) {
      const consumedAttempts = discovery && config.interleave ? phaseUsage.discoveryAttempts : budget.httpAttempts;
      const consumedTokens = discovery && config.interleave ? phaseUsage.discoveryInputTokens : budget.inputTokens;
      if (budget.httpAttempts >= config.maxAttempts || budget.inputTokens + estimate > config.maxInputTokens || consumedAttempts >= attemptsCeiling || consumedTokens + estimate > ceiling) {
        budget.stopped = budget.httpAttempts >= attemptsCeiling ? "attempt-budget" : "token-budget";
        addTrace("request-deferred", { phase, estimate, budget: { ...budget } });
        return null;
      }
      const before = { ...budget };
      budget.httpAttempts++;
      if (discovery) phaseUsage.discoveryAttempts++;
      try {
        const result = await runtime.sendFindImageJudgment(request, uploads, "V5 · " + phase);
        const usage = result.usage;
        if (Number.isInteger(usage?.input_tokens) && usage.input_tokens >= 0) {
          budget.inputTokens += usage.input_tokens;
          if (discovery) phaseUsage.discoveryInputTokens += usage.input_tokens;
          estimateRatio = Math.max(estimateRatio, usage.input_tokens / Math.max(1, estimate / estimateRatio));
        } else budget.unknownUsageAttempts++;
        if (Number.isInteger(usage?.output_tokens) && usage.output_tokens >= 0) budget.outputTokens += usage.output_tokens;
        addTrace("request", { phase, requestId: budget.httpAttempts, crops: items.map(i => ({ region: i.crop.region, content: i.crop.content, width: i.crop.width, height: i.crop.height })), answers: result.answers, before, after: { ...budget } });
        if (budget.unknownUsageAttempts) budget.stopped = "unknown-token-usage";
        return result.answers || {};
      } catch (error) {
        budget.failedAttempts++;
        if (Number.isInteger(error.usage?.input_tokens) && error.usage.input_tokens >= 0) budget.inputTokens += error.usage.input_tokens;
        else budget.unknownUsageAttempts++;
        if (Number.isInteger(error.usage?.output_tokens) && error.usage.output_tokens >= 0) budget.outputTokens += error.usage.output_tokens;
        addTrace("request-failed", { phase, status: error.status, error: String(error.message), before, after: { ...budget } });
        // An unknown bill cannot be treated as free budget. Preserve failure as incomplete evidence.
        if (budget.unknownUsageAttempts || retry === 3 || ![429,502,503,504,529].includes(error.status)) {
          budget.stopped = "service-failure";
          return null;
        }
        await (runtime.delay || (ms => new Promise(resolve => setTimeout(resolve, ms))))(1000 * 2 ** retry);
      }
    }
  }
  function split(region, reason) {
    if (region.depth >= config.maxDepth) { issues.push({ reason: "depth-limit", region: region.core, trigger: reason }); return; }
    const children = createFindGridRegions(region, 2, 2, config.halo, bitmap.width, bitmap.height);
    if (children.length !== 4) { issues.push({ reason: "crop-limit", region: region.core, trigger: reason }); return; }
    queue.push(...children.map(r=>({...r,priority:reason==="three_or_more" ? 3 : reason==="two" ? 2 : 1})));
    addTrace("split", { reason, region: region.core });
  }
  function captureObservation(i,r,count,boxAnswer,index,mapped,origin) {
        const discovery = discoveryDecision(count,config.discoveryGate,config.aggregatePresence);
        const box = mapped ? mapBoxToPhoto(mapped,root) : null;
        if (box) {
          const observation = { id:"O"+(observations.length+1), box, sourceBox:mapped,
            sourceCrop:i.crop.region,cropContent:i.crop.content,depth:r.depth,core:r.core,
            confidence:boxAnswer.confidence,count,discovery,requestId:budget.httpAttempts,
            origin, knownInstances:(i.known || []).map(k=>k.box), boundary:["left","top","right","bottom"].filter(edge=>Math.abs(mapped[edge]-i.crop.region[edge])<.01) };
          observations.push(observation);
          addTrace("observation",{observationId:observation.id,observation});
          if (!discovery.pass) addTrace("candidate-rejected",{observationId:observation.id,stage:"multiplicity",reason:discovery.reason});
        } else {
          const rejection = {requestId:budget.httpAttempts,index,reason:"geometry-invalid",rawBox:boxAnswer?.box ?? null,count};
          geometryRejections.push(rejection); addTrace("candidate-rejected",{stage:"geometry",...rejection});
        }
  }
  async function locateAdditional() {
    if (!config.additionalPositions || budget.stopped) return;
    const regions=additionalRegions.slice(0,config.maxAdditionalRegions);
    const pending=regions.flatMap(({region,count})=>["leftmost","rightmost"].map(position=>({region,count,position})));
    for (const group of chunks(pending,config.batchSize)) {
      const items=await Promise.all(group.map(async x=>({...await item(x.region.crop),...x})));
      const answers=await send(items,"additional",true);
      if (!answers) {issues.push({reason:"additional-search-incomplete",pending:group.length});break;}
      items.forEach((i,index)=>{
        const answer=answers["r"+index+"_box"];
        const mapped=validBox(answer?.box) ? mapCropBoxToPreparedImage(answer.box,i.crop) : null;
        captureObservation(i,i.region,i.count,answer,index,mapped,"additional-"+i.position);
      });
    }
  }
  async function verifyPending() {
    // Reserved discovery allowance is not the total allowance: use the reserve for checks.
    if (["attempt-budget","token-budget"].includes(budget.stopped) && budget.httpAttempts < config.maxAttempts && budget.inputTokens < config.maxInputTokens) {
      addTrace("discovery-reserve-reached", { reason:budget.stopped });
      budget.stopped = null;
    }
    // Verify every positive observation, retaining boundary/halo evidence. Refinement is an opt-in ablation.
    const pendingObservations = observations.filter(o => !processedObservations.has(o.id) && (o.discovery.pass || config.auditAllCandidates));
    for (const batch of chunks(pendingObservations, config.batchSize)) {
      if (budget.stopped) break;
      const items = await Promise.all(batch.map(async o => ({ ...await item(contextRegion(o.sourceBox, bitmap.width, bitmap.height, config.contextFactor), config.cleanRefinement ? null : o.sourceBox), observation: o })));
      const proposed = config.refine ? await send(items, "refine") : {};
      if (!proposed) break;
      const verification = [];
      for (let i = 0; i < items.length; i++) {
        const o = batch[i];
        const answer = proposed["r" + i + "_box"];
        const box = config.refine ? (validBox(answer?.box) ? mapCropBoxToPreparedImage(answer.box, items[i].crop) : null) : o.sourceBox;
        // Only nominate overlapping same-instance proposals; final semantic checks decide acceptance.
        if (!box || boxIntersectionArea(box, o.sourceBox) === 0) { issues.push({ reason: "invalid-refinement", observationId: o.id }); continue; }
        const crop = config.refine ? await item(contextRegion(box, bitmap.width, bitmap.height, config.contextFactor), [
          { box: o.sourceBox, color: "#286aff" }, { box, color: "#ff3828" }]) : null;
        const clean = await item(box);
        verification.push({ ...clean, identityCrop:crop?.crop, identityReference:crop?.reference,identityPart:crop?.part, observation:o,proposedBox:box });
        addTrace(config.refine ? "refinement-proposed" : "localization-retained", { observationId: o.id, before: o.sourceBox, after: box });
      }
      if (!verification.length) continue;
      const verified = await send(verification, "verify");
      if (!verified) break;
      verification.forEach((i,index) => {
        const presence = probability(verified["r" + index + "_presence"]?.noul);
        const edgeProbabilities = Object.fromEntries(["left","top","right","bottom"].map(edge => [edge, probability(verified["r"+index+"_cut_"+edge]?.noul)]));
        const completeness = Object.values(edgeProbabilities).every(p => p !== null) ? 1 - Math.max(...Object.values(edgeProbabilities)) : null;
        const identity = config.refine ? verified["r" + index + "_identity"] : {choice:"same",probabilities:{same:1},reason:"unchanged-localization"};
        const box = mapBoxToPhoto(i.proposedBox, root);
        const instanceCount = verified["r" + index + "_instance_count"] ?? null;
        const v = { box, sourceBox:i.proposedBox, presence, completeness, edgeProbabilities, identity, instanceCount };
        i.observation.verification = v;
        processedObservations.add(i.observation.id);
        const decision = verificationDecision(v, config);
        const pass = i.observation.discovery.pass && decision.pass;
        addTrace(pass ? "candidate-verified" : "candidate-provisional", { observationId: i.observation.id, presence, completeness, edgeProbabilities, identity, proposedBox: i.proposedBox, reasons: [...(i.observation.discovery.pass ? [] : [i.observation.discovery.reason]), ...decision.reasons] });
        if (pass && box) accepted.push({ ...i.observation, initialBox: i.observation.box, box, sourceBox: i.proposedBox, presence, completeness, edgeProbabilities, instanceCount, localizationState:completeness !== null && completeness >= config.completenessGate ? "complete" : "needs-review", identity });
        else if (i.observation.discovery.pass) issues.push({ reason: "unverified-candidate", observationId: i.observation.id });
      });
    }
  }
  async function identifyPending() {
    // Nominate nearby pairs. A high IoU is still not permission to merge two individuals.
    const pairs = [];
    for (let a = 0; a < accepted.length; a++) for (let b = a + 1; b < accepted.length; b++) {
      const x = accepted[a], y = accepted[b];
      if (!comparedPairs.has(pairKey(x.id,y.id)) && (config.auditAllPairs || identityPairNeeded(x,y,config.includeSourcePairs))) pairs.push({left:x,right:y});
    }
    pairs.sort((a,b) => boxIntersectionArea(b.left.box,b.right.box)/Math.max(1e-9,Math.min(boxArea(b.left.box),boxArea(b.right.box))) - boxIntersectionArea(a.left.box,a.right.box)/Math.max(1e-9,Math.min(boxArea(a.left.box),boxArea(a.right.box))));
    while (pairs.length) {
      const current = resolveIdentities(accepted,relationships);
      const owner = new Map(current.objects.flatMap(o => o.observationIds.map(id => [id,o.id])));
      // A known different-instance constraint already answers comparisons between
      // these groups. Repeating them wastes budget and can manufacture conflicts.
      pairs.sort((a,b) => {
        const impact = p => (current.objects.find(o=>o.id===owner.get(p.left.id))?.observationIds.length || 1) * (current.objects.find(o=>o.id===owner.get(p.right.id))?.observationIds.length || 1);
        return impact(b)-impact(a);
      });
      const pending = pairs.splice(0,config.batchSize).filter(p => {
        const a=owner.get(p.left.id),b=owner.get(p.right.id);
        if (a===b || (!config.auditAllPairs && config.skipKnownDifferent && knownDifferent(a,b,owner,relationships))) {
          addTrace("identity-implied",{left:p.left.id,right:p.right.id,decision:a===b ? "same" : "different"});
          return false;
        }
        return true;
      });
      if (!pending.length) continue;
      const items = budget.stopped ? [] : await Promise.all(pending.map(async p => ({ ...await item(paddedPairRegion(p.left.sourceBox,p.right.sourceBox,bitmap.width,bitmap.height), [
        { box:p.left.sourceBox,color:"#ff3828" },{ box:p.right.sourceBox,color:"#286aff" }]), pair:p })));
      const answers = items.length ? await send(items,"identity") : null;
      pending.forEach((pair,index) => {
        const raw = answers?.["r"+index+"_identity"];
        const same = probability(raw?.probabilities?.same), different = probability(raw?.probabilities?.different);
        const decision = raw?.choice === "same" && same !== null && same >= config.sameGate ? "same"
          : raw?.choice === "different" && different !== null && different >= config.differentGate ? "different" : "uncertain";
        const relation = { left:pair.left.id,right:pair.right.id,decision,raw };
        comparedPairs.add(pairKey(pair.left.id,pair.right.id));
        relationships.push(relation);addTrace("identity",relation);
      });
    }
  }
  try {
    while (queue.length && checked < config.maxRegions && !budget.stopped) {
      queue.sort((a,b)=>(b.global || b.minimum ? 100 : b.priority || 0)-(a.global || a.minimum ? 100 : a.priority || 0));
      const batch = queue.splice(0, Math.min(config.batchSize, config.maxRegions - checked));
      const items = await Promise.all(batch.map(async r => {
        // Minimum coverage stays clean and comparable. Adaptive crops explicitly
        // seek new identities rather than repeatedly selecting the same center.
        const known = config.recoverDistinct && !r.minimum && !r.global ? resolveIdentities(accepted,relationships).objects
          .filter(o => boxIntersectionArea(o.sourceBox,r.crop) / boxArea(o.sourceBox) > .95).map(o => ({box:o.sourceBox,color:"#286aff"})) : [];
        return { ...await item(r.crop,known.length ? known : null), region:r, known };
      }));
      const answers = await send(items, "discover", true);
      if (!answers) { queue.unshift(...batch); break; }
      items.forEach((i,index) => {
        const r = i.region, count = answers["r" + index + "_count"], boxAnswer = answers["r" + index + "_box"];
        checked++;
        if (r.minimum) minimumChecked++;
        const choices = { none: 0, one: 1, two: 2, three_or_more: 3 };
        const known = Object.hasOwn(choices, count?.choice);
        const p = probability(count?.probabilities?.[count?.choice]);
        if (r.global && known && p !== null && p >= .5) globalMinimum = choices[count.choice];
        if (r.global && config.aggregatePresence && discoveryDecision(count,config.discoveryGate,true).pass) globalMinimum=Math.max(1,globalMinimum);
        const mapped = validBox(boxAnswer?.box) ? mapCropBoxToPreparedImage(boxAnswer.box, i.crop) : null;
        captureObservation(i,r,count,boxAnswer,index,mapped,"discover");
        if (config.additionalPositions && known && ["two","three_or_more"].includes(count.choice) && p !== null && p >= config.discoveryGate) additionalRegions.push({region:r,count});
        if (r.global) return; // Global evidence cannot cancel minimum coverage.
        if (known && count.choice === "none" && p !== null && p >= .8) return;
        if (known && count.choice === "one" && p !== null && p >= config.discoveryGate && mapped) return;
        split(r, known ? count.choice : "invalid-count");
      });
      if (config.interleave) { await verifyPending(); await identifyPending(); }
      runtime.state.findProgress = { checked, calls: budget.httpAttempts, found: resolveIdentities(accepted,relationships).objects.filter(o=>o.identityState==="resolved").length, pending: queue.length };
      runtime.updateFindProgress(target);
    }
    await locateAdditional();
    await verifyPending();
    await identifyPending();
    const registry = resolveIdentities(accepted,relationships);
    const confirmed = registry.objects.filter(o => o.identityState === "resolved");
    const displayBox = o => ({ ...o, preparedBox: {
      left: prepared.content.left + o.box.left * (prepared.content.right-prepared.content.left),
      right: prepared.content.left + o.box.right * (prepared.content.right-prepared.content.left),
      top: prepared.content.top + o.box.top * (prepared.content.bottom-prepared.content.top),
      bottom: prepared.content.top + o.box.bottom * (prepared.content.bottom-prepared.content.top) } });
    const boxes = confirmed.map(displayBox);
    const reviewBoxes = registry.objects.filter(o=>o.identityState!=="resolved").map(displayBox);
    const coverage = { expected: expectedMinimum, completed: minimumChecked, complete: minimumChecked === expectedMinimum };
    if (globalMinimum > confirmed.length) issues.push({ reason: "global-local-contradiction", minimum: globalMinimum, confirmed: confirmed.length });
    const processed = new Set(trace.filter(t => ["candidate-verified","candidate-provisional"].includes(t.action)).map(t => t.observationId));
    const provisional = observations.filter(o => o.discovery.pass && !accepted.some(a => a.id === o.id));
    const unprocessed = observations.filter(o => o.discovery.pass && !processed.has(o.id));
    const localizationReview = boxes.filter(o=>o.localizationState!=="complete").length;
    const unresolved = issues.length + queue.length + registry.unresolvedGroups + unprocessed.length + localizationReview + (budget.stopped ? 1 : 0);
    const termination = [...new Set([...(budget.stopped ? [budget.stopped] : []),...issues.map(i=>i.reason),...(queue.length ? [checked >= config.maxRegions ? "region-budget" : "coverage-incomplete"] : []),...(registry.unresolvedGroups ? ["unresolved-identity"] : []),...(localizationReview ? ["localization-review"] : [])])];
    addTrace("terminated", { termination, coverage, budget: { ...budget } });
    const result = { imageId, mode:"all", version:"v5", evidenceVersion:2, boxes, reviewBoxes, geometryRejections, acceptedObservationIds:accepted.map(o=>o.id), clusters:[], checked, apiRequests:budget.httpAttempts, unresolved,
      localizationReview:boxes.filter(o=>o.localizationState!=="complete").length, confirmedCount:boxes.filter(o=>o.localizationState==="complete").length, pendingRegions:queue.length, pendingIndividuals:unprocessed.length, policyVersion:FIND_POLICY_VERSION, config, observations, relationships, registry, provisional, issues, coverage,
      budget, phaseUsage, termination:termination.length ? termination : ["queue-exhausted"], trace };
    result.acceptance = replayV5Evidence(result).decisions;
    return result;
  } finally { bitmap.close(); }
}
