/** V6 per-search settings. Values are model gates, not measured accuracy. */
import { FIND_ALL_LIMITS } from "./limits.js";

export const V6_SETTINGS = Object.freeze([
  { key:"minChoiceConfidence", label:"Split regions below this count confidence", help:"Higher values subdivide more uncertain regions, using more search work." },
  { key:"minBoxConfidence", label:"Verify boxes below this box confidence", help:"Higher values send more boxes for verification; this is a check trigger, not a display cutoff." },
  { key:"minV3BoxCheckProbability", label:"Minimum verification probability", help:"Higher values accept fewer checked boxes. Rejected boxes may trigger subdivision." },
  { key:"minDuplicatePairProbability", label:"Minimum same-object merge probability", help:"Higher values require stronger model evidence to merge two observations." },
  { key:"duplicateBoxIou", label:"Duplicate-box overlap threshold (IoU)", help:"Higher values suppress fewer pairs using this overlap rule. Other duplicate rules still apply. This is separate from benchmark IoU." },
].map(field => Object.freeze(field)));
export const V6_DEFAULT_CONFIG = Object.freeze({ ...FIND_ALL_LIMITS });

export function resolveV6Config(overrides = {}) {
  if (!overrides || typeof overrides !== "object" || Array.isArray(overrides)) throw new Error("V6 settings must be an object.");
  const allowed = new Set(V6_SETTINGS.map(field => field.key));
  for (const [key,value] of Object.entries(overrides)) {
    if (!allowed.has(key) || typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1)
      throw new Error("Invalid V6 setting: " + key + ". Use a probability from 0 to 1.");
  }
  return Object.freeze({ ...V6_DEFAULT_CONFIG, ...overrides });
}
export function isCustomV6Config(config) {
  return V6_SETTINGS.some(({key}) => config[key] !== V6_DEFAULT_CONFIG[key]);
}
