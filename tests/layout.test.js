import test from 'node:test';
import assert from 'node:assert/strict';
import { buildLayoutRequest, summarizeLayout, LAYOUT_POLICY, layoutProbability } from '../web/layout.js';

test('optional checks require evidence and assets match uploaded parts', () => {
  const basic = buildLayoutRequest('');
  assert.deepEqual(Object.keys(basic.questions), ['clipping', 'overlap', 'readability']);
  const paired = buildLayoutRequest('a table and a world map', true);
  assert.equal(paired.questions.requirements.type, 'noul');
  assert.equal(paired.questions.fidelity.type, 'noul');
  assert.equal(paired.assets[paired.state.referencePage].part, 'reference');
  assert.equal(paired.assets[paired.state.renderedPage].part, 'rendered');
});
test('any high issue overrides low scores and uncertainty needs review', () => {
  assert.equal(summarizeLayout({a:{noul:0.1},b:{noul:0.7}}, ['a','b']), 'Potential issues found');
  assert.equal(summarizeLayout({a:{noul:0.31}}, ['a']), 'Needs review');
  assert.equal(summarizeLayout({a:{noul:0.3}}, ['a']), 'No issues flagged');
});
test('missing or invalid API answers never produce a passing report', () => {
  for (const value of [undefined, null, '0.2', NaN, Infinity, -0.1, 1.1]) {
    assert.throws(() => summarizeLayout({a:{noul:value}}, ['a']), /invalid/);
  }
  assert.throws(() => summarizeLayout({}, ['a']));
});

test('assessed policy keeps conservative thresholds and versioned reports', () => {
  assert.equal(LAYOUT_POLICY.issue, 0.7);
  assert.equal(LAYOUT_POLICY.reviewAbove, 0.3);
  assert.equal(LAYOUT_POLICY.version, 'layout-v3');
  assert.ok(Object.isFrozen(LAYOUT_POLICY));
});

test('overlap categories preserve coexistence and use the calibrated boundary', () => {
  const choice = (overlap_only, clipping_only, both, neither) => ({type:'choice',probabilities:{overlap_only,clipping_only,both,neither}});
  const clipped=choice(.02,.93,.01,.04);
  assert.ok(Math.abs(layoutProbability(clipped,'overlap')-.03)<1e-10);
  assert.equal(summarizeLayout({overlap:clipped},['overlap']),'No issues flagged');
  const coexist=choice(.1,.05,.8,.05);
  assert.equal(summarizeLayout({clipping:{noul:.95},overlap:coexist},['overlap']),'Potential issues found');
  assert.equal(summarizeLayout({overlap:choice(.35,.1,.25,.3)},['overlap']),'Potential issues found');
  assert.equal(summarizeLayout({overlap:choice(.3,.1,.29,.31)},['overlap']),'Needs review');
  assert.equal(LAYOUT_POLICY.overlapIssue,.6);
});
test('invalid category distributions cannot become a passing overlap check', () => {
  for (const probabilities of [{}, {overlap_only:.1,clipping_only:.1,both:.1,neither:.1}, {overlap_only:.4,clipping_only:.2,both:NaN,neither:.4}]) {
    assert.throws(()=>layoutProbability({type:'choice',probabilities},'overlap'),/invalid/);
  }
});
