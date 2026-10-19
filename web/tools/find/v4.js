/**
 * Find Objects V4: V3-style refinement on a 2×2 grid, with separate clickable group references.
 * Cluster references are not individual detections and never contribute to the object count.
 * The shared combined loop executes this version's policy without duplicating search logic.
 */
import { findAllObjectsCombined } from "./combined.js";

export const V4_STRATEGY = Object.freeze({ rows: 2, columns: 2, initialHalo: 0.14, splitHalo: 0.16, split: "quadrants", batchSize: 16 });

export function selectV4Strategy(preparedImage, canvasWidth, canvasHeight) {
  return V4_STRATEGY;
}

export function findAllObjectsV4(preparedImage, imageId, target, runtime) {
  return findAllObjectsCombined(preparedImage, imageId, target, "v4", selectV4Strategy, runtime);
}
