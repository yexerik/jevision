/** Reversible identity resolution. Geometry only nominates pairs, never deletes evidence. */
export function resolveIdentities(observations, relationships) {
  const groups = new Map(observations.map(o => [o.id, new Set([o.id])]));
  const different = relationships.filter(r => r.decision === "different");
  const conflicts = [];
  for (const relation of relationships.filter(r => r.decision === "same")) {
    const a = groups.get(relation.left), b = groups.get(relation.right);
    if (!a || !b || a === b) continue;
    if (different.some(r => (a.has(r.left) && b.has(r.right)) || (b.has(r.left) && a.has(r.right)))) {
      conflicts.push({ ...relation, reason: "different-instance-constraint" });
      continue;
    }
    const merged = new Set([...a, ...b]);
    merged.forEach(id => groups.set(id, merged));
  }
  const unique = [...new Set(groups.values())];
  const uncertain = [...relationships.filter(r => r.decision === "uncertain"), ...conflicts];
  const unresolved = uncertain.filter(r => groups.get(r.left) !== groups.get(r.right));
  const provisionalIds = new Set(unresolved.flatMap(r => [...(groups.get(r.left) || []), ...(groups.get(r.right) || [])]));
  const objects = unique.map(ids => {
    const supports = observations.filter(o => ids.has(o.id));
    // Select a verified observation; never union/average boxes or discard originals.
    const preferred = [...supports].sort((a,b) => (b.completeness ?? 0) - (a.completeness ?? 0) || (b.presence ?? 0) - (a.presence ?? 0))[0];
    return { ...preferred, id: [...ids].sort()[0], observationIds: [...ids], identityState: [...ids].some(id => provisionalIds.has(id)) ? "uncertain" : "resolved" };
  });
  // Count connected unresolved relationship groups, not pair edges or objects.
  const adjacency = new Map();
  for (const r of unresolved) {
    const a = groups.get(r.left), b = groups.get(r.right);
    if (!adjacency.has(a)) adjacency.set(a, new Set());
    if (!adjacency.has(b)) adjacency.set(b, new Set());
    adjacency.get(a).add(b); adjacency.get(b).add(a);
  }
  let unresolvedGroups = 0;
  const seen = new Set();
  for (const group of adjacency.keys()) {
    if (seen.has(group)) continue;
    unresolvedGroups++;
    const queue = [group];
    while (queue.length) {
      const next = queue.pop();
      if (seen.has(next)) continue;
      seen.add(next); queue.push(...adjacency.get(next));
    }
  }
  return { objects, conflicts, unresolvedGroups };
}
