/**
 * Historical Find Objects V1–V4 limits and acceptance gates.
 * These settings are preserved for baseline comparisons; they are not V5 calibration results.
 */
export const FIND_ALL_LIMITS = { batchSize: 16, maxRegions: 255, maxApiRequests: 96, maxDepth: 7, minCropPixels: 32, splitHalo: 0.06, minChoiceConfidence: 0.25, minBoxConfidence: 0.5, minBoxCheckProbability: 0.7, minV3BoxCheckProbability: 0.65, duplicateBoxIou: 0.5, duplicateBoxCoverage: 0.2, minDuplicatePairProbability: 0.55, maxDuplicatePairsPerBatch: 12 };
