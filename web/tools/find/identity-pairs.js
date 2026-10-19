import { boxArea, boxIntersectionArea, boxCenterDistance } from './geometry.js';

export const pairKey = (a,b) => [a,b].sort().join(':');
export function identityPairNeeded(x,y,includeSourcePairs = false) {
  const overlap = boxIntersectionArea(x.box,y.box) / Math.max(1e-9,Math.min(boxArea(x.box),boxArea(y.box)));
  const sharedSingleCrop = x.count?.choice === 'one' && y.count?.choice === 'one' && x.sourceCrop && y.sourceCrop &&
    boxIntersectionArea(x.sourceCrop,y.sourceCrop) / Math.max(1e-9,Math.min(boxArea(x.sourceCrop),boxArea(y.sourceCrop))) >= .8;
  return overlap >= .1 || (includeSourcePairs && sharedSingleCrop) || boxCenterDistance(x.box,y.box) < Math.sqrt(Math.min(boxArea(x.box),boxArea(y.box))) * .5;
}

export function knownDifferent(a,b,registry,relationships) {
  return relationships.some(r => r.decision === 'different' &&
    ((registry.get(r.left) === a && registry.get(r.right) === b) || (registry.get(r.left) === b && registry.get(r.right) === a)));
}
