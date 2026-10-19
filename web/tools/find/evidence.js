/** Acceptance is pure: saved judgments can be replayed without another model call.
 * Missing checks stay missing; relaxed replay cannot invent counterfactual answers.
 */
import { identityPairNeeded, pairKey, knownDifferent } from './identity-pairs.js';
import { resolveIdentities } from './registry.js';

export const probability = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;
export function discoveryDecision(count, gate = .5, aggregatePresence = false) {
  const known = ['none', 'one', 'two', 'three_or_more'].includes(count?.choice);
  const p = probability(count?.probabilities?.[count?.choice]);
  if (aggregatePresence && known && p !== null) {
    const hasNone = Object.hasOwn(count.probabilities, 'none');
    const none = probability(count.probabilities.none);
    if (hasNone && none === null) return {pass:false,reason:'multiplicity-invalid',presenceProbability:null};
    // one/two/three_or_more partition the event "a target exists". Uncertainty
    // between those positive counts must not be mistaken for uncertain presence.
    // Partial fixtures without P(none) supply only a conservative lower bound.
    const presenceProbability = none !== null ? 1-none : count.choice === 'none' ? 0 : p;
    const pass = presenceProbability >= gate;
    return {pass, reason:pass ? null : 'discovery-presence-threshold',presenceProbability,
      probabilityBasis:none !== null ? 'one-minus-none' : 'positive-class-lower-bound'};
  }
  return { pass: known && count.choice !== 'none' && p !== null && p >= gate,
    reason: !known || p === null ? 'multiplicity-missing' : count.choice === 'none' ? 'multiplicity-none' : p < gate ? 'multiplicity-threshold' : null };
}

export function verificationDecision(v, config) {
  const reasons = [];
  if (!v) return { pass: false, reasons: ['verification-not-run'] };
  if (probability(v.presence) === null) reasons.push('presence-missing');
  else if (v.presence < config.presenceGate) reasons.push('presence-threshold');
  const count = v.instanceCount;
  if (config.rejectMultiple && !count) reasons.push('multiplicity-check-not-run');
  if (config.rejectMultiple && ['two','three_or_more'].includes(count?.choice) && probability(count?.probabilities?.[count.choice]) !== null && count.probabilities[count.choice] >= config.verificationCountGate) reasons.push('multiple-instances');
  if (config.strictCompleteness && (probability(v.completeness) === null || v.completeness < config.completenessGate)) reasons.push('extent-threshold');
  if (config.refine && (v.identity?.choice !== 'same' || probability(v.identity?.probabilities?.same) === null || v.identity.probabilities.same < config.refinementIdentityGate)) reasons.push('refinement-identity');
  if (!v.box) reasons.push('geometry-invalid');
  return { pass: reasons.length === 0, reasons };
}

export function replayV5Evidence(result, overrides = {}) {
  if (result.evidenceVersion !== 2) throw new Error('Replay requires V5 evidence version 2; old logs omit rejected boxes/checks.');
  const allowed = new Set(["verificationCountGate","discoveryGate","presenceGate","completenessGate","sameGate","differentGate","refinementIdentityGate","strictCompleteness","rejectMultiple","aggregatePresence"]);
  for (const key of Object.keys(overrides)) if (!allowed.has(key)) throw new Error("Replay cannot change search or question semantics: " + key);
  const config = { verificationCountGate:.8, aggregatePresence:false, ...result.config, ...overrides };
  for (const key of ['verificationCountGate', 'discoveryGate', 'presenceGate', 'completenessGate', 'sameGate', 'differentGate', 'refinementIdentityGate'])
    if (probability(config[key]) === null) throw new Error('Invalid replay threshold: ' + key);
  for (const key of ["strictCompleteness","rejectMultiple","aggregatePresence"]) if (typeof config[key] !== "boolean" && config[key] !== undefined) throw new Error("Invalid replay flag: " + key);
  const decisions = [], accepted = [];
  for (const o of result.observations) {
    const discovery = discoveryDecision(o.count, config.discoveryGate, config.aggregatePresence);
    const verification = verificationDecision(o.verification, config);
    const reasons = [...(discovery.pass ? [] : [discovery.reason]), ...verification.reasons];
    decisions.push({ observationId: o.id, geometry:'valid', ownership:'not-applied', discovery: discovery.pass, verification: verification.pass, reasons });
    if (discovery.pass && verification.pass) accepted.push({ ...o, ...o.verification,
      localizationState: o.verification.completeness !== null && o.verification.completeness >= config.completenessGate ? 'complete' : 'needs-review' });
  }
  const ids = new Set(accepted.map(o => o.id));
  const relationships = result.relationships.filter(r => ids.has(r.left) && ids.has(r.right)).map(r => {
    const raw = r.raw, same = probability(raw?.probabilities?.same), different = probability(raw?.probabilities?.different);
    return { ...r, decision: raw?.choice === 'same' && same !== null && same >= config.sameGate ? 'same'
      : raw?.choice === 'different' && different !== null && different >= config.differentGate ? 'different' : 'uncertain' };
  });
  let registry = resolveIdentities(accepted, relationships);
  const owner = new Map(registry.objects.flatMap(o=>o.observationIds.map(id=>[id,o.id])));
  const recorded = new Set(relationships.map(r=>pairKey(r.left,r.right)));
  const missingPairs=[];
  for (let a=0;a<accepted.length;a++) for(let b=a+1;b<accepted.length;b++) {
    const x=accepted[a],y=accepted[b],left=owner.get(x.id),right=owner.get(y.id);
    if (left===right || knownDifferent(left,right,owner,relationships) || recorded.has(pairKey(x.id,y.id))) continue;
    if (config.auditAllPairs || identityPairNeeded(x,y,config.includeSourcePairs)) missingPairs.push({left:x.id,right:y.id,decision:'uncertain',missing:true});
  }
  // Newly accepted singletons are unassessed even if geometry nominates no pair:
  // their acceptance was never exercised in the recorded execution.
  const oldAccepted = new Set(result.acceptedObservationIds || []);
  const newlyAccepted = accepted.filter(o => !oldAccepted.has(o.id));
  registry = resolveIdentities(accepted,[...relationships,...missingPairs]);
  const affected=new Set(missingPairs.flatMap(r=>[r.left,r.right]).concat(newlyAccepted.map(o=>o.id)));
  for (const o of registry.objects) if (o.observationIds.some(id=>affected.has(id))) o.identityState='unassessed';
  const boxes = registry.objects.filter(o => o.identityState === 'resolved');
  const reviewBoxes = registry.objects.filter(o => o.identityState !== 'resolved');
  for (const o of registry.objects) for (const id of o.observationIds) {
    const d = decisions.find(d => d.observationId === id);
    d.identity = o.identityState;
    if (o.id !== id) d.reasons.push('same-instance-merged');
    if (o.identityState !== 'resolved') d.reasons.push('identity-' + o.identityState);
  }
  return { config, decisions, accepted, registry, boxes, reviewBoxes,
    missingVerification: decisions.filter(d => d.reasons.includes('verification-not-run')).length,
    missingIdentity: registry.objects.filter(o=>o.identityState==='unassessed').length, missingPairs,
    scope: 'Fixed recorded observations and checks only; no new crops or invented answers.' };
}
