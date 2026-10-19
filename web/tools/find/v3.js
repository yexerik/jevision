/**
 * Find Objects V3: Adaptive grid with a full-photo probe, box refinement, and model-assisted duplicate checks.
 * The shared combined loop executes this version's policy without duplicating search logic.
 */
import { findAllObjectsCombined } from "./combined.js";

export const V3_STRATEGY = Object.freeze({ rows: 3, columns: 3, initialHalo: 0.16, splitHalo: 0.16, split: "quadrants", batchSize: 16 });

export function selectV3Strategy(preparedImage, canvasWidth, canvasHeight) {
  const contentWidth = (preparedImage.content.right - preparedImage.content.left) * canvasWidth;
  const contentHeight = (preparedImage.content.bottom - preparedImage.content.top) * canvasHeight;
  // Use unpadded content and a local copy so small runs cannot mutate later runs.
  if (Math.min(contentWidth / V3_STRATEGY.columns, contentHeight / V3_STRATEGY.rows) < 220) {
    return { ...V3_STRATEGY, rows: 2, columns: 2, split: "binary" };
  }
  return V3_STRATEGY;
}

export function findAllObjectsV3(preparedImage, imageId, target, runtime) {
  return findAllObjectsCombined(preparedImage, imageId, target, "v3", selectV3Strategy, runtime);
}
