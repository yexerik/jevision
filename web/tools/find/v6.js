/**
 * Experimental V6 starts from the V4 baseline, with its own search policy modules.
 * No accuracy improvement is claimed by this initial fork. V4 remains unchanged.
 */
import { resolveV6Config } from "./v6/config.js";
import { findAllObjectsCombined } from "./v6/combined.js";

export const V6_STRATEGY = Object.freeze({ rows: 2, columns: 2, initialHalo: 0.14, splitHalo: 0.16, split: "quadrants", batchSize: 16 });

export function selectV6Strategy() {
  return V6_STRATEGY;
}

export async function findAllObjectsV6(preparedImage, imageId, target, runtime) {
  const config = resolveV6Config(runtime.v6Config);
  const result = await findAllObjectsCombined(preparedImage, imageId, target, "v6", selectV6Strategy, runtime, config);
  return { ...result, config: { ...config, strategy: { ...V6_STRATEGY } } };
}
