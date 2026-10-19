/**
 * Find Objects V2: Combined Count + Box baseline: 2×2 grid, binary splits, and bounded empty-region retries.
 * The shared combined loop executes this version's policy without duplicating search logic.
 */
import { findAllObjectsCombined } from "./combined.js";

export const V2_STRATEGY = Object.freeze({ rows: 2, columns: 2, initialHalo: 0.12, splitHalo: 0.12, split: "binary", batchSize: 16, minNoneConfidence: 0.6, maxNoneRefinementDepth: 2 });

export function selectV2Strategy(preparedImage, canvasWidth, canvasHeight) {
  return V2_STRATEGY;
}

export function findAllObjectsV2(preparedImage, imageId, target, runtime) {
  return findAllObjectsCombined(preparedImage, imageId, target, "v2", selectV2Strategy, runtime);
}
